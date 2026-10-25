"""Training entry point with resumable state and selection on validation SNR."""
import argparse
import copy
import csv
import json
import math
import os
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from .data import DEFAULT_SOURCES, MUSDBDataset, load_manifest
from .losses import separation_loss
from .metrics import metrics_per_source


# A bounded recovery guard, not a claim that this is a universally optimal limit.
MAX_CONSECUTIVE_AMP_OVERFLOWS = 8


def restore_scaler_state(scaler, saved_state):
    """Restore AMP state only when the current run uses an enabled scaler.

    AMP -> FP32 deliberately ignores the saved scaler. FP32 -> AMP starts with
    a fresh scale because disabled scalers save an empty state dictionary.
    """
    if not scaler.is_enabled():
        return "disabled"
    if saved_state:
        scaler.load_state_dict(saved_state)
        return "restored"
    return "fresh"


def checked_optimizer_step(model, optimizer, scaler, *, step=0, ema=None,
                           ema_decay=0.999, max_norm=5.0):
    """Unscale once, recover AMP overflow, and update EMA after real steps only.

    The norm is accumulated in float64: a float32 sum of squares can overflow
    even when every gradient entry is finite. This distinguishes that case from
    the nonfinite entries GradScaler detects and skips. Returned diagnostics do
    not infer which operation originally produced a nonfinite gradient.
    """
    if max_norm <= 0:
        raise ValueError("max_norm must be positive")
    scaler.unscale_(optimizer)
    parameters = [parameter for parameter in model.parameters() if parameter.grad is not None]
    if not parameters:
        raise ValueError("No gradients to update")
    finite_entries = bool(torch.stack([torch.isfinite(parameter.grad).all()
                                      for parameter in parameters]).all())
    scale_before = float(scaler.get_scale())
    if not finite_entries:
        if not scaler.is_enabled():
            optimizer.zero_grad(set_to_none=True)
            raise FloatingPointError("Nonfinite FP32 gradient entries; inspect loss/data/model.")
        # unscale_ recorded the inf/NaN entries. GradScaler skips optimizer.step
        # and update backs off its scale; do not clip or update EMA in this case.
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)
        return {"stepped": False, "step": step, "gradient_entries_finite": False,
                "grad_norm": None, "scale_before": scale_before,
                "scale_after": float(scaler.get_scale())}
    with torch.no_grad():
        norms = torch.stack([torch.linalg.vector_norm(parameter.grad, dtype=torch.float64)
                             for parameter in parameters])
        norm = torch.linalg.vector_norm(norms)
        if not bool(torch.isfinite(norm)):
            optimizer.zero_grad(set_to_none=True)
            raise FloatingPointError("Nonfinite float64 gradient norm despite finite entries; no optimizer step.")
        coefficient = (max_norm / (norm + 1e-6)).clamp(max=1.0)
        for parameter in parameters:
            parameter.grad.mul_(coefficient)
    scaler.step(optimizer)
    scaler.update()
    optimizer.zero_grad(set_to_none=True)
    step += 1
    if ema is not None:
        decay = min(ema_decay, (1 + step) / (10 + step))
        with torch.no_grad():
            for average, current in zip(ema.parameters(), model.parameters()):
                average.lerp_(current.detach(), 1 - decay)
            for average, current in zip(ema.buffers(), model.buffers()):
                average.copy_(current)
    return {"stepped": True, "step": step, "gradient_entries_finite": True,
            "grad_norm": float(norm), "scale_before": scale_before,
            "scale_after": float(scaler.get_scale())}


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def atomic_save(obj, path):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(obj, temporary)
    os.replace(temporary, path)


def build_model(kind, config):
    if kind == "lite":
        from .model import DemucsLiteV2
        return DemucsLiteV2(**config)
    from .pretrained import PretrainedSeparator
    return PretrainedSeparator(**config)


@torch.inference_mode()
def validate(model, loader, device, amp, loss_config):
    model.eval()
    values, masks, si_values = [], [], []
    total, count = 0.0, 0
    for mix, target in tqdm(loader, desc="Validation", leave=False):
        mix, target = mix.to(device), target.to(device)
        with torch.autocast(device.type, enabled=amp):
            estimate = model(mix)
        loss, _ = separation_loss(estimate, target, mix, **loss_config)
        metrics = metrics_per_source(estimate, target)
        values.append(metrics["snr_db"].cpu())
        si_values.append(metrics["si_sdr_db"].cpu())
        masks.append(metrics["active"].cpu())
        total += loss.item() * len(mix)
        count += len(mix)
    values, si_values, masks = torch.cat(values), torch.cat(si_values), torch.cat(masks)
    # Equal track weight, then equal source weight; silent crops are excluded.
    n_tracks = len(loader.dataset.records)
    n_crops = count // n_tracks
    mask = masks.reshape(n_tracks, n_crops, -1)
    per_track = []
    for tensor in (values, si_values):
        x = tensor.reshape(n_tracks, n_crops, -1)
        active_count = mask.sum(1)
        track_score = (x * mask).sum(1) / active_count.clamp_min(1)
        track_score[active_count == 0] = float("nan")
        per_track.append(torch.nanmean(track_score, dim=0))
    snr, si = per_track
    if not torch.isfinite(snr).any():
        raise ValueError("No active validation targets.")
    result = {"loss": total / count, "snr_db": float(torch.nanmean(snr)),
              "si_sdr_db": float(torch.nanmean(si))}
    for i, source in enumerate(model.sources):
        result[f"snr_{source}_db"] = float(snr[i])
        result[f"si_sdr_{source}_db"] = float(si[i])
        result[f"active_{source}"] = float(masks[:, i].float().mean())
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--kind", choices=["lite", "pretrained"], default="lite")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--accumulate", type=int, default=4)
    p.add_argument("--segment", type=float, default=6)
    p.add_argument("--train-crops", type=int, default=32)
    p.add_argument("--val-crops", type=int, default=8)
    p.add_argument("--channels", type=int, default=32)
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--lr", type=float)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--spectral-weight", type=float, default=0.05)
    p.add_argument("--si-sdr-weight", type=float, default=0.01)
    p.add_argument("--ema-decay", type=float, default=0.999)
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--no-amp", action="store_true")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = p.parse_args()
    if min(args.epochs, args.batch_size, args.accumulate, args.train_crops, args.val_crops) <= 0:
        p.error("Epochs, batch size, accumulation and crops must be positive.")
    if not 0 <= args.ema_decay < 1:
        p.error("EMA decay must be in [0,1).")
    seed_all(args.seed)
    device = torch.device(args.device)
    amp = device.type == "cuda" and not args.no_amp
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = ({"sources": DEFAULT_SOURCES, "channels": args.channels, "depth": args.depth}
              if args.kind == "lite" else {"name": "htdemucs", "sources": DEFAULT_SOURCES})
    saved = None
    if args.resume:
        saved = torch.load(run_dir / "last.pth", map_location="cpu", weights_only=False)
        if saved["model_kind"] != args.kind:
            raise ValueError("Cannot resume a different architecture.")
        config = saved["model_config"]
    elif (run_dir / "last.pth").exists():
        raise FileExistsError("Run already exists. Use --resume or a new run-dir.")
    model = build_model(args.kind, config).to(device)
    if args.kind == "pretrained":
        args.segment = min(args.segment, model.segment)
    learning_rate = args.lr if args.lr is not None else (3e-4 if args.kind == "lite" else 1e-5)
    loss_config = {"spectral_weight": args.spectral_weight, "si_sdr_weight": args.si_sdr_weight,
                   "consistency_weight": 0.1}
    records = load_manifest(args.manifest)
    train_records = [r for r in records if r["subset"] == "train"]
    val_records = [r for r in records if r["subset"] == "val"]
    if not train_records or not val_records:
        raise ValueError("Manifest must contain train and val tracks.")
    train_data = MUSDBDataset(train_records, sources=model.sources, segment_seconds=args.segment,
                             crops_per_track=args.train_crops, training=True, seed=args.seed)
    val_data = MUSDBDataset(val_records, sources=model.sources, segment_seconds=args.segment,
                           training=False, validation_crops=args.val_crops, seed=args.seed)
    generator = torch.Generator().manual_seed(args.seed)
    loader_options = {"num_workers": args.workers, "pin_memory": device.type == "cuda",
                      "persistent_workers": False}
    train_loader = DataLoader(train_data, args.batch_size, shuffle=True, generator=generator, **loader_options)
    val_loader = DataLoader(val_data, args.batch_size, shuffle=False, **loader_options)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5,
                                                         patience=5, min_lr=learning_rate / 30)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    ema = copy.deepcopy(model).eval() if args.ema_decay else None
    if ema is not None:
        ema.requires_grad_(False)
    start, best, stale, step = 1, -math.inf, 0, 0
    history = []
    amp_overflows_total, consecutive_overflows = 0, 0
    # Resume only identical data/loss/training settings; number of epochs may grow.
    settings = vars(args).copy()
    settings["lr"] = learning_rate
    settings["amp_enabled"] = amp
    settings["precision_mode"] = "cuda_amp" if amp else "fp32"
    if saved:
        for key in ("segment", "train_crops", "val_crops", "batch_size", "accumulate", "seed",
                    "ema_decay", "weight_decay", "spectral_weight", "si_sdr_weight", "lr"):
            if saved["training_config"][key] != settings[key]:
                raise ValueError(f"Resume config changed: {key}. Start a new run.")
        if saved["manifest"] != records or saved["loss_config"] != loss_config:
            raise ValueError("Resume requires identical manifest and loss.")
        model.load_state_dict(saved["model_state_dict"])
        if ema is not None:
            ema.load_state_dict(saved["ema_state_dict"])
        optimizer.load_state_dict(saved["optimizer_state_dict"])
        scheduler.load_state_dict(saved["scheduler_state_dict"])
        scaler_restoration = restore_scaler_state(scaler, saved.get("scaler_state_dict", {}))
        previous_amp = saved["training_config"].get("amp_enabled", bool(saved.get("scaler_state_dict")))
        settings["resume_precision_from"] = "cuda_amp" if previous_amp else "fp32"
        print(f"Resume precision: {settings['resume_precision_from']} -> {settings['precision_mode']}; "
              f"scaler {scaler_restoration}", flush=True)
        start, best, stale, step = saved["epoch"] + 1, saved["best_snr_db"], saved["stale"], saved["step"]
        amp_overflows_total = saved.get("amp_overflows_total", 0)
        consecutive_overflows = saved.get("consecutive_amp_overflows", 0)
        history = saved["history"]
        torch.set_rng_state(saved["rng_torch"])
        random.setstate(saved["rng_python"])
        np.random.set_state(saved["rng_numpy"])
        generator.set_state(saved["rng_loader"])
        if device.type == "cuda" and saved.get("rng_cuda") is not None:
            torch.cuda.set_rng_state_all(saved["rng_cuda"])
    (run_dir / "config.json").write_text(json.dumps(settings, indent=2))

    def checkpoint(epoch, selected="raw"):
        return {"format_version": 2, "model_kind": args.kind, "model_config": model.export_config(),
                "sources": list(model.sources), "sample_rate": 44100,
                "model_state_dict": model.state_dict(),
                "ema_state_dict": ema.state_dict() if ema is not None else None,
                "selected_weights": selected, "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(), "scaler_state_dict": scaler.state_dict(),
                "epoch": epoch, "step": step, "best_snr_db": best, "stale": stale,
                "amp_overflows_total": amp_overflows_total,
                "consecutive_amp_overflows": consecutive_overflows,
                "training_config": settings, "loss_config": loss_config, "history": history,
                "manifest": records, "rng_torch": torch.get_rng_state(),
                "rng_python": random.getstate(), "rng_numpy": np.random.get_state(),
                "rng_loader": generator.get_state(),
                "rng_cuda": torch.cuda.get_rng_state_all() if device.type == "cuda" else None}

    # Retain pretrained baseline if fine-tuning makes validation worse.
    if not saved and args.kind == "pretrained":
        baseline = validate(model, val_loader, device, amp, loss_config)
        best = baseline["snr_db"]
        history.append({"epoch": 0, "train_loss": None, "lr": learning_rate, "selected": "raw",
                        "precision_mode": settings["precision_mode"], "amp_skipped_groups": 0,
                        "amp_overflows_total": 0, "amp_scale": float(scaler.get_scale()), **baseline})
        atomic_save(checkpoint(0), run_dir / "best.pth")
        export_best(run_dir)
    for epoch in range(start, args.epochs + 1):
        train_data.set_epoch(epoch)
        model.train()
        total, count = 0.0, 0
        skipped_groups = 0
        optimizer.zero_grad(set_to_none=True)
        for batch_idx, (mix, target) in enumerate(tqdm(train_loader, desc=f"Epoch {epoch}/{args.epochs}")):
            mix, target = mix.to(device, non_blocking=True), target.to(device, non_blocking=True)
            with torch.autocast(device.type, enabled=amp):
                estimate = model(mix)
            loss, _ = separation_loss(estimate, target, mix, **loss_config)
            if not torch.isfinite(loss):
                raise FloatingPointError("Nonfinite loss. Retry with --no-amp and inspect dataset.")
            group_start = (batch_idx // args.accumulate) * args.accumulate
            divisor = min(args.accumulate, len(train_loader) - group_start)
            scaler.scale(loss / divisor).backward()
            if (batch_idx + 1) % args.accumulate == 0 or batch_idx + 1 == len(train_loader):
                update = checked_optimizer_step(model, optimizer, scaler, step=step,
                                                ema=ema, ema_decay=args.ema_decay)
                step = update["step"]
                if update["stepped"]:
                    consecutive_overflows = 0
                else:
                    skipped_groups += 1
                    amp_overflows_total += 1
                    consecutive_overflows += 1
                    print(f"AMP nonfinite gradient entries: skipped group at epoch {epoch}, "
                          f"batch {batch_idx + 1}; scale {update['scale_before']:g} -> "
                          f"{update['scale_after']:g}; consecutive {consecutive_overflows}/"
                          f"{MAX_CONSECUTIVE_AMP_OVERFLOWS}; optimizer/EMA unchanged", flush=True)
                    if consecutive_overflows >= MAX_CONSECUTIVE_AMP_OVERFLOWS:
                        raise FloatingPointError(
                            f"AMP has {consecutive_overflows} consecutive nonfinite-gradient groups; "
                            "stopped without changing the best checkpoint. Resume --no-amp "
                            "or inspect loss/data/model.")
            total += loss.item() * len(mix)
            count += len(mix)
        raw_metrics = validate(model, val_loader, device, amp, loss_config)
        selected, val = "raw", raw_metrics
        if ema is not None:
            ema_metrics = validate(ema, val_loader, device, amp, loss_config)
            if ema_metrics["snr_db"] > val["snr_db"]:
                selected, val = "ema", ema_metrics
        learning_rate_used = optimizer.param_groups[0]["lr"]
        scheduler.step(val["snr_db"])
        improved = val["snr_db"] > best + 1e-4
        best, stale = (val["snr_db"], 0) if improved else (best, stale + 1)
        history.append({"epoch": epoch, "train_loss": total / count, "lr": learning_rate_used,
                        "selected": selected, "precision_mode": settings["precision_mode"],
                        "amp_skipped_groups": skipped_groups,
                        "amp_overflows_total": amp_overflows_total,
                        "amp_scale": float(scaler.get_scale()), **val})
        state = checkpoint(epoch, selected)
        atomic_save(state, run_dir / "last.pth")
        if improved:
            atomic_save(state, run_dir / "best.pth")
            # Keep a deployable export even if a later epoch/runtime is interrupted.
            export_best(run_dir)
        with (run_dir / "history.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(history[-1]))
            writer.writeheader()
            writer.writerows(history)
        print(json.dumps(history[-1]), flush=True)
        if args.patience and stale >= args.patience:
            print("Early stopping: validation SNR has stopped improving.")
            break
    export_best(run_dir)


def export_best(run_dir):
    run_dir = Path(run_dir)
    best = torch.load(run_dir / "best.pth", map_location="cpu", weights_only=False)
    state = best["ema_state_dict"] if best["selected_weights"] == "ema" else best["model_state_dict"]
    export = {k: best[k] for k in ("format_version", "model_kind", "model_config", "sources", "sample_rate", "epoch", "best_snr_db")}
    export["model_state_dict"] = state
    export["ema_state_dict"] = None
    export["selected_weights"] = best["selected_weights"]
    atomic_save(export, run_dir / "best_model.pth")
    print(f"Exported {run_dir / 'best_model.pth'} (epoch {best['epoch']}, val SNR {best['best_snr_db']:.3f} dB)")


if __name__ == "__main__":
    main()
