"""Full-track comparison: median 1s window SNR/SI-SDR, then macro over tracks."""
import argparse
import json
from pathlib import Path

import torch
from torch import nn
from tqdm import tqdm

from .data import DEFAULT_SOURCES, load_manifest
from .inference import load_audio, load_checkpoint, overlap_add, separate_official
from .metrics import metrics_per_source


def legacy_model(checkpoint, device="cpu"):
    from .legacy_model import DemucsLite
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg = ckpt.get("model_config", {"channels": 32, "depth": 5})
    backbone = DemucsLite(sources=4, audio_channels=2, **cfg)
    backbone.load_state_dict(ckpt.get("model_state_dict", ckpt))

    class LegacyWrapper(nn.Module):
        sources = DEFAULT_SOURCES
        samplerate = 44100

        def __init__(self):
            super().__init__()
            self.backbone = backbone

        def forward(self, mix):
            return self.backbone(mix)

    return LegacyWrapper().to(device).eval()


def window_scores(estimate, target, sr=44100):
    rows = []
    for start in range(0, target.shape[-1], sr):
        ref = target[..., start:start + sr]
        est = estimate[..., start:start + sr]
        if ref.shape[-1] < sr // 2:
            continue
        rows.append(metrics_per_source(est[None], ref[None]))
    if not rows:
        rows = [metrics_per_source(estimate[None], target[None])]
    result = {}
    active = torch.cat([r["active"] for r in rows])
    for key in ("snr_db", "si_sdr_db"):
        scores = torch.cat([r[key] for r in rows])
        result[key] = [float(scores[:, i][active[:, i]].median()) if active[:, i].any() else None
                       for i in range(len(DEFAULT_SOURCES))]
    result["active_ratio"] = active.float().mean(0).tolist()
    silent = torch.cat([r["silent_estimate_energy"] for r in rows])
    result["silent_estimate_rms"] = [float(silent[:, i][~active[:, i]].mean().sqrt())
                                     if (~active[:, i]).any() else None for i in range(4)]
    return result


def summarize_tracks(rows):
    """Keep the primary macro metric identical, and handle an empty filtered view."""
    if not rows:
        return None
    summary = {}
    for key in ("snr_db", "si_sdr_db"):
        scores = torch.tensor([[float("nan") if x is None else x for x in r[key]] for r in rows],
                              dtype=torch.float32)
        per_source = torch.nanmean(scores, 0)
        summary[key] = {source: float(per_source[i]) for i, source in enumerate(DEFAULT_SOURCES)}
        summary[f"macro_{key}"] = float(torch.nanmean(per_source))
    return summary


def evaluation_report(rows, settings):
    """Report all tracks first, with a separate diagnostic view of flagged mixes.

    Neither view changes the inference audio or targets. The filtered view is
    explicitly secondary, so a known dataset anomaly cannot silently improve
    the advertised all-track score.
    """
    flagged = [row for row in rows if row.get("known_issue")]
    unflagged = [row for row in rows if not row.get("known_issue")]
    return {
        "settings": settings,
        "sources": list(DEFAULT_SOURCES),
        "mixture_policy": "original_mixture_wav",
        "metric_definition": "Median active 1-second window per track; arithmetic mean over tracks and sources. SNR is scale-dependent energy ratio, not BSS Eval SDR.",
        "summary": summarize_tracks(rows),
        "summary_without_flagged_tracks": summarize_tracks(unflagged),
        "track_counts": {"all": len(rows), "without_flagged": len(unflagged), "flagged": len(flagged)},
        "flagged_tracks": [
            {key: row[key] for key in ("track_name", "known_issue", "residual_policy") if key in row}
            for row in flagged
        ],
        "tracks": rows,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--checkpoint")
    choice.add_argument("--legacy-checkpoint")
    choice.add_argument("--official", choices=["htdemucs", "htdemucs_ft"])
    p.add_argument("--subset", choices=["val", "test"], default="test")
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--shifts", type=int, default=2)
    args = p.parse_args()
    records = [r for r in load_manifest(args.manifest) if r["subset"] == args.subset]
    if args.limit:
        records = records[:args.limit]
    if not records:
        raise ValueError("No evaluation tracks.")
    if args.official:
        from .compat import official_model
        model = official_model(args.official).eval()
    elif args.legacy_checkpoint:
        model = legacy_model(args.legacy_checkpoint, args.device)
    else:
        model, _ = load_checkpoint(args.checkpoint, args.device)
    rows = []
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    for record in tqdm(records, desc=f"Full-track {args.subset}"):
        directory = Path(record["path"])
        mixture = load_audio(directory / "mixture.wav")
        if args.official:
            estimate = separate_official(mixture, args.official, args.device,
                                         args.shifts, model=model)
        else:
            estimate = overlap_add(model, mixture, segment_seconds=10 if args.legacy_checkpoint else 6,
                                   device=args.device)
            estimate = estimate[[model.sources.index(s) for s in DEFAULT_SOURCES]]
        target = torch.stack([load_audio(directory / f"{source}.wav") for source in DEFAULT_SOURCES])
        if estimate.shape != target.shape:
            raise ValueError("Sample alignment changed during inference.")
        provenance = {key: record[key] for key in
                      ("known_issue", "residual_policy", "max_probe_residual_rms_by_channel")
                      if key in record}
        rows.append({"track_name": record["track_name"], **provenance, **window_scores(estimate, target)})
        # Partial readback survives a disconnected Colab session.
        path.write_text(json.dumps({"settings": vars(args), "sources": list(DEFAULT_SOURCES),
                                    "mixture_policy": "original_mixture_wav", "tracks": rows}, indent=2))
    report = evaluation_report(rows, vars(args))
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
