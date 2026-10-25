"""Bounded-memory inference and lossless float WAV export."""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch.nn import functional as F

from .data import DEFAULT_SOURCES


def load_audio(path, sample_rate=44100):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if not np.isfinite(data).all() or not len(data):
        raise ValueError("Audio must be nonempty and finite.")
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    if data.shape[1] != 2:
        raise ValueError("Provide mono/stereo audio; explicitly downmix multichannel input.")
    wav = torch.from_numpy(np.ascontiguousarray(data.T))
    if sr != sample_rate:
        from torchaudio.functional import resample
        wav = resample(wav, sr, sample_rate)
    return wav


def load_checkpoint(path, device="cpu", use_ema=None):
    # Only load checkpoints created by this project or other trusted sources.
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    if ckpt.get("format_version") != 2:
        raise ValueError("Expected V2 checkpoint. Original weights require the original architecture.")
    if ckpt["model_kind"] == "lite":
        from .model import DemucsLiteV2
        model = DemucsLiteV2(**ckpt["model_config"])
    elif ckpt["model_kind"] == "pretrained":
        from .pretrained import PretrainedSeparator
        model = PretrainedSeparator(**ckpt["model_config"])
    else:
        raise ValueError("Unknown checkpoint architecture.")
    if use_ema is None:
        use_ema = ckpt.get("selected_weights") == "ema"
    state = ckpt.get("ema_state_dict") if use_ema else None
    model.load_state_dict(state if state is not None else ckpt["model_state_dict"])
    model.to(device).eval()
    return model, ckpt


@torch.inference_mode()
def overlap_add(model, mixture, segment_seconds=6.0, overlap=0.5, device="cpu"):
    """CPU full-song buffers; only one context window occupies accelerator memory."""
    if mixture.ndim != 2 or mixture.shape[-1] == 0:
        raise ValueError("Expected nonempty [channels,time] mixture.")
    if not 0 <= overlap < 1 or segment_seconds <= 0:
        raise ValueError("Positive segment and overlap in [0,1) required.")
    model.eval()
    sr = getattr(model, "samplerate", 44100)
    segment = max(1, round(segment_seconds * sr))
    if hasattr(model, "segment"):
        segment = min(segment, round(float(model.segment) * sr))
    hop = max(1, round(segment * (1 - overlap)))
    # Context on both boundaries avoids giving endpoints zero overlap weight.
    margin = segment // 2
    cpu_mix = mixture.detach().float().cpu()
    padded = F.pad(cpu_mix, (margin, margin))
    output = torch.zeros(len(model.sources), mixture.shape[0], padded.shape[-1])
    weights = torch.zeros(padded.shape[-1])
    window = torch.hann_window(segment, periodic=False).clamp_min(1e-3)
    for start in range(0, padded.shape[-1], hop):
        valid = min(segment, padded.shape[-1] - start)
        chunk = F.pad(padded[:, start:start + valid], (0, segment - valid))
        pred = model(chunk[None].to(device))[0, ..., :valid].float().cpu()
        output[..., start:start + valid] += pred * window[:valid]
        weights[start:start + valid] += window[:valid]
    output /= weights.clamp_min(1e-8)
    return output[..., margin:margin + cpu_mix.shape[-1]]


@torch.inference_mode()
def separate_official(mixture, name="htdemucs_ft", device="cpu", shifts=2, overlap=0.5, segment=7.8, model=None):
    from demucs.apply import apply_model
    from .compat import official_model
    # Keep ensemble on CPU: official apply_model moves one member at a time.
    model = official_model(name).eval() if model is None else model.eval()
    mixture = mixture.detach().float().cpu()
    if mixture.ndim != 2 or mixture.shape[0] != 2 or not mixture.shape[-1] or not torch.isfinite(mixture).all():
        raise ValueError("Expected finite nonempty stereo audio.")
    if shifts < 0 or not 0 <= overlap < 1 or segment <= 0:
        raise ValueError("Invalid shifts, overlap or segment.")
    reference = mixture.mean(dim=0)
    mean = reference.mean()
    std = reference.std(unbiased=False).clamp_min(1e-5)
    normalized = (mixture - mean) / std
    maximum = getattr(model, "max_allowed_segment", segment)
    segment = min(segment, float(maximum))
    result = apply_model(model, normalized[None], device=device, shifts=shifts,
                         split=True, overlap=overlap, segment=segment, progress=True)[0]
    result = result.float().cpu() * std + mean / len(model.sources)
    order = [model.sources.index(s) for s in DEFAULT_SOURCES]
    return result[order]


def save_stems(estimates, directory, sources=DEFAULT_SOURCES, sr=44100):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not torch.isfinite(estimates).all():
        raise ValueError("Nonfinite model estimates cannot be exported.")
    # FLOAT preserves amplitudes above 1 instead of silently clipping PCM16.
    for source, estimate in zip(sources, estimates):
        sf.write(directory / f"{source}.wav", estimate.cpu().numpy().T, sr, subtype="FLOAT")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--official", choices=["htdemucs", "htdemucs_ft"])
    choice.add_argument("--checkpoint")
    p.add_argument("--output", required=True)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--segment", type=float)
    p.add_argument("--overlap", type=float, default=0.5)
    p.add_argument("--shifts", type=int, default=2)
    args = p.parse_args()
    wav = load_audio(args.input)
    if args.official:
        result = separate_official(wav, args.official, args.device, args.shifts,
                                   args.overlap, min(args.segment or 7.8, 7.8))
        sources = DEFAULT_SOURCES
    else:
        model, _ = load_checkpoint(args.checkpoint, args.device)
        result = overlap_add(model, wav, args.segment or 6, args.overlap, args.device)
        sources = model.sources
    save_stems(result, args.output, sources)
    Path(args.output, "inference.json").write_text(json.dumps(vars(args), indent=2))


if __name__ == "__main__":
    main()
