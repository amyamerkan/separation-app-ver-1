"""Audited MUSDB18-HQ loading and stereo, source-consistent augmentation.

MUSDB18-HQ contains 100 physical training tracks and 50 test tracks.  The
official 14 validation tracks are selected by name, before drawing any crops.
Never split segments from one song across training and validation.

The exact PR - Oh No test track has a documented left-channel erratum and an
additional observed right-channel residual. Its residuals are warnings under
the explicit known-track policy; original benchmark mixture/stems are preserved.
https://sigsep.github.io/datasets/musdb.html#errata
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import warnings
from typing import Sequence

import numpy as np
import soundfile as sf
import torch
from torch.utils.data import Dataset

DEFAULT_SOURCES = ("vocals", "drums", "bass", "other")
# https://github.com/sigsep/sigsep-mus-db/blob/master/musdb/configs/mus.yaml
VALIDATION_TRACKS = frozenset(
    (
        "Actions - One Minute Smile",
        "Clara Berry And Wooldog - Waltz For My Victims",
        "Johnny Lokke - Promises & Lies",
        "Patrick Talbot - A Reason To Leave",
        "Triviul - Angelsaint",
        "Alexander Ross - Goodbye Bolero",
        "Fergessen - Nos Palpitants",
        "Leaf - Summerghost",
        "Skelpolu - Human Mistakes",
        "Young Griffo - Pennies",
        "ANiMAL - Rockshow",
        "James May - On The Line",
        "Meaxic - Take A Step",
        "Traffic Experiment - Sirens",
    )
)
_ALL_FILES = ("mixture", *DEFAULT_SOURCES)
KNOWN_LEFT_MIX_ERRATUM = "musdb18hq_pr_oh_no_left_mixture"
KNOWN_MIX_RESIDUAL_POLICY = "warn_known_artistic_mix"
MUSDB_ERRATA_URL = "https://sigsep.github.io/datasets/musdb.html#errata"


def _write_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_manifest(records: Sequence[dict], path: str | Path) -> None:
    """Save metadata; audio is neither copied nor downloaded."""
    _write_json(path, {"schema_version": 1, "sources": list(DEFAULT_SOURCES), "tracks": list(records)})


def load_manifest(path: str | Path, root: str | Path | None = None) -> list[dict]:
    """Read a manifest, optionally relocating its paths under a new dataset root."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else payload["tracks"]
    records = [dict(record) for record in records]
    if root is not None:
        root = Path(root).expanduser().resolve()
        for record in records:
            relative = Path(record["relative_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe relative_path for {record['track_name']}: {relative}")
            record["path"] = str(root / relative)
    return records


def _quantization_step(subtype: str) -> float:
    return {"PCM_U8": 2.0**-7, "PCM_S8": 2.0**-7, "PCM_16": 2.0**-15,
            "PCM_24": 2.0**-23, "PCM_32": 2.0**-31}.get(subtype, 0.0)


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))


def scan_dataset(
    root: str | Path,
    output: str | Path | None = None,
    strict: bool = True,
    *,
    audit_output: str | Path | None = None,
    probe_seconds: float = 1.0,
    allow_known_errata: bool = True,
) -> list[dict]:
    """Audit and index a local MUSDB18-HQ WAV dataset.

    Required layout: ``root/train/<song>/{mixture,vocals,drums,bass,other}.wav``
    and ``root/test/<song>/...``. A wrapping directory under ``root`` is allowed.
    ``strict=False`` relaxes dataset counts only, for small development fixtures.
    Every WAV must still be 44.1 kHz stereo with an identical, positive length.

    Three spread probes per song check finite samples, stem activity, and the
    residual between mixture and sum of stems. WAV rounding is tolerated: the
    warning floor is five quantization steps; a much larger residual raises an
    error because it suggests an alignment or export problem. These probes do
    not certify every sample; the loader checks every crop it reads as well.

    By default, only physical ``test/PR - Oh No`` permits residuals on both
    channels: the left is documented by SigSep, the right is additionally
    observed in the supplied dataset and is not attributed to that errata.
    Shape, finite samples and every other song remain checked as before.
    ``allow_known_errata=False`` rejects residuals on either channel. The scanner
    does not modify audio, replace the original mixture or exclude the track.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {root}")
    if probe_seconds <= 0:
        raise ValueError("probe_seconds must be positive")
    candidates = sorted(root.rglob("mixture.wav"))
    if not candidates:
        raise ValueError(f"No mixture.wav found in {root}; extract MUSDB18-HQ first.")
    records: list[dict] = []
    audits: list[dict] = []
    errors: list[str] = []
    messages: list[str] = []
    physical_names: dict[str, set[str]] = {"train": set(), "test": set()}
    for mixture_path in candidates:
        track_path = mixture_path.parent
        track_name = track_path.name
        split = track_path.parent.name
        label = f"{split}/{track_name}"
        known_issue = KNOWN_LEFT_MIX_ERRATUM if split == "test" and track_name == "PR - Oh No" else None
        residual_policy = (KNOWN_MIX_RESIDUAL_POLICY if allow_known_errata else "reject_residuals") if known_issue else None
        if split not in physical_names:
            errors.append(f"{label}: expected track directly under train/ or test/.")
            continue
        if track_name in physical_names[split]:
            errors.append(f"{label}: duplicate track name (possibly two dataset copies).")
            continue
        physical_names[split].add(track_name)
        infos: dict[str, sf.SoundFile] = {}
        track_errors: list[str] = []
        for name in _ALL_FILES:
            path = track_path / f"{name}.wav"
            if not path.is_file():
                track_errors.append(f"missing {name}.wav")
                continue
            try:
                infos[name] = sf.info(path)
            except (RuntimeError, sf.LibsndfileError) as exc:
                track_errors.append(f"cannot read {name}.wav: {exc}")
        if "mixture" in infos:
            expected = infos["mixture"]
            for name, info in infos.items():
                if info.samplerate != 44100 or info.channels != 2:
                    track_errors.append(f"{name}.wav: expected 44100 Hz stereo, got {info.samplerate} Hz/{info.channels} channels")
                if info.frames <= 0 or info.frames != expected.frames:
                    track_errors.append(f"{name}.wav: {info.frames} frames, mixture has {expected.frames}")
        if track_errors:
            errors.extend(f"{label}: {error}" for error in track_errors)
            audits.append({"track_name": track_name, "physical_subset": split,
                           "known_issue": known_issue, "residual_policy": residual_policy, "errors": track_errors})
            continue
        expected = infos["mixture"]
        length = min(expected.frames, max(1, round(probe_seconds * expected.samplerate)))
        offsets = sorted(set((0, (expected.frames - length) // 2, expected.frames - length)))
        probes = []
        quantization = max(_quantization_step(info.subtype) for info in infos.values())
        for offset in offsets:
            audio = {
                name: sf.read(track_path / f"{name}.wav", start=offset, frames=length,
                              always_2d=True, dtype="float32")[0]
                for name in _ALL_FILES
            }
            if any(value.shape != (length, 2) or not np.isfinite(value).all() for value in audio.values()):
                errors.append(f"{label}: non-finite samples or a truncated read at frame {offset}")
                continue
            summed = np.sum([audio[source].astype(np.float64) for source in DEFAULT_SOURCES], axis=0)
            residual = audio["mixture"] - summed
            residual_rms = _rms(residual)
            mixture_rms = _rms(audio["mixture"])
            residual_db = 20 * np.log10(max(residual_rms, 1e-12) / max(mixture_rms, 1e-12))
            channel_diagnostics = {}
            for index, channel in enumerate(("left", "right")):
                channel_residual = _rms(residual[:, index])
                channel_mixture = _rms(audio["mixture"][:, index])
                channel_diagnostics[channel] = {
                    "residual_rms": channel_residual,
                    "residual_relative_db": float(20 * np.log10(max(channel_residual, 1e-12)
                                                                 / max(channel_mixture, 1e-12))),
                    "residual_peak": float(np.max(np.abs(residual[:, index]))),
                    "warning_floor": max(5 * quantization, 1e-5, channel_mixture * 1e-3),
                    "failure_floor": max(20 * quantization, 0.01, channel_mixture * 0.05),
                }
            probe = {
                "start_frame": offset,
                "frames": length,
                "rms": {name: _rms(value) for name, value in audio.items()},
                "active_fraction": {
                    name: float(np.mean(np.max(np.abs(value), axis=1) > 1e-4))
                    for name, value in audio.items()
                },
                "residual_rms": residual_rms,
                "residual_relative_db": float(residual_db),
                "residual_peak": float(np.max(np.abs(residual))),
                "residual_by_channel": channel_diagnostics,
            }
            probes.append(probe)
            warning_floor = max(5 * quantization, 1e-5, mixture_rms * 1e-3)
            failure_floor = max(20 * quantization, 0.01, mixture_rms * 0.05)
            if known_issue:
                # Narrow exception for this physical test track only. Keep diagnostics
                # on both channels; a right mismatch is observed, not official errata.
                for channel, diagnostic in channel_diagnostics.items():
                    rms = diagnostic["residual_rms"]
                    db = diagnostic["residual_relative_db"]
                    if allow_known_errata and rms > diagnostic["warning_floor"]:
                        description = ("known MUSDB erratum on left channel; mixture/stem residual"
                                       if channel == "left" else "additional observed right-channel residual")
                        provenance = (MUSDB_ERRATA_URL if channel == "left"
                                      else "observed in supplied dataset; official erratum describes the left channel")
                        messages.append(f"{label}: {description} RMS {rms:.5g} ({db:.1f} dB) at frame {offset}; "
                                        f"policy {KNOWN_MIX_RESIDUAL_POLICY}; original mixture/stems retained; {provenance}")
                    elif rms > diagnostic["failure_floor"]:
                        errors.append(f"{label}: {channel} channel mixture/stem residual RMS {rms:.5g} "
                                      f"({db:.1f} dB) at frame {offset}; check alignment/export")
                    elif rms > diagnostic["warning_floor"]:
                        messages.append(f"{label}: {channel} channel mixture/stem residual RMS {rms:.5g} "
                                        f"({db:.1f} dB) at frame {offset}")
            elif residual_rms > failure_floor:
                errors.append(f"{label}: mixture/stem residual RMS {residual_rms:.5g} ({residual_db:.1f} dB) at frame {offset}; check alignment/export")
            elif residual_rms > warning_floor:
                messages.append(f"{label}: mixture/stem residual RMS {residual_rms:.5g} ({residual_db:.1f} dB) at frame {offset}")
        if probes and all(probe["rms"]["mixture"] < 1e-5 for probe in probes):
            messages.append(f"{label}: all mixture probes are nearly silent; inspect the song.")
        subset = "val" if split == "train" and track_name in VALIDATION_TRACKS else split
        record = {
            "track_name": track_name, "subset": subset, "physical_subset": split,
            "path": str(track_path), "relative_path": str(track_path.relative_to(root)),
            "frames": expected.frames, "sample_rate": expected.samplerate, "channels": expected.channels,
            "max_probe_residual_rms_by_channel": {
                channel: max((probe["residual_by_channel"][channel]["residual_rms"] for probe in probes), default=None)
                for channel in ("left", "right")
            },
        }
        if known_issue:
            record["known_issue"] = known_issue
            record["residual_policy"] = residual_policy
        records.append(record)
        audits.append({"track_name": track_name, "subset": subset, "known_issue": known_issue,
                       "residual_policy": residual_policy, "probes": probes})
    overlap = physical_names["train"] & physical_names["test"]
    if overlap:
        errors.append(f"Training/test track-name overlap: {sorted(overlap)}")
    if strict:
        for split, count in (("train", 100), ("test", 50)):
            if len(physical_names[split]) != count:
                errors.append(f"Expected {count} physical {split} tracks, found {len(physical_names[split])}")
        missing_validation = VALIDATION_TRACKS - physical_names["train"]
        if missing_validation:
            errors.append(f"Missing official validation tracks: {sorted(missing_validation)}")
    counts = {subset: sum(record["subset"] == subset for record in records) for subset in ("train", "val", "test")}
    if audit_output is None and output is not None:
        output_path = Path(output)
        audit_output = output_path.with_name(output_path.stem + ".audit.json")
    audit = {"schema_version": 1, "root": str(root), "counts": counts,
             "probe_seconds": probe_seconds, "warnings": messages, "errors": errors, "tracks": audits,
             "known_errata_policy": {"allow_known_errata": bool(allow_known_errata),
                                     "issue": KNOWN_LEFT_MIX_ERRATUM, "source": MUSDB_ERRATA_URL,
                                     "official_erratum_channels": ["left"],
                                     "additional_observed_residual_channels": ["right"],
                                     "residual_policy": KNOWN_MIX_RESIDUAL_POLICY if allow_known_errata else "reject_residuals",
                                     "original_mixture_stems_preserved": True}}
    if audit_output is not None:
        _write_json(audit_output, audit)
    if errors:
        raise ValueError("Dataset audit failed:\n- " + "\n- ".join(errors))
    for message in messages:
        warnings.warn(message, stacklevel=2)
    if output is not None:
        save_manifest(records, output)
    return records


class MUSDBDataset(Dataset):
    """Random training crops or deterministic spread validation crops.

    Returns ``(mixture[2,T], targets[S,2,T])`` in ``sources`` order. Random
    source remixing is restricted to the supplied training records. Source gain,
    polarity and stereo-channel swapping always affect both channels together;
    the augmented mixture is built *after* augmentation as the exact stem sum.
    A common scale avoids clipping without normalizing stems independently.

    Call ``set_epoch`` before creating each epoch's DataLoader iterator and use
    ``persistent_workers=False`` so workers receive the new deterministic seed.
    """

    def __init__(
        self,
        records: Sequence[dict],
        sources: Sequence[str] = DEFAULT_SOURCES,
        segment_seconds: float = 6.0,
        sample_rate: int = 44100,
        training: bool = True,
        crops_per_track: int = 32,
        remix_prob: float = 0.5,
        gain_db: float = 3.0,
        seed: int = 42,
        validation_crops: int = 3,
    ):
        self.records = [dict(record) for record in records]
        self.sources = tuple(sources)
        self.sample_rate = int(sample_rate)
        self.segment_frames = round(segment_seconds * self.sample_rate)
        self.training = bool(training)
        self.crops_per_track = int(crops_per_track if training else validation_crops)
        self.remix_prob = float(remix_prob)
        self.gain_db = float(gain_db)
        self.seed = int(seed)
        self.epoch = 0
        if not self.records:
            raise ValueError("No dataset records supplied")
        if self.sample_rate != 44100 or self.segment_frames <= 0:
            raise ValueError("MUSDB18-HQ requires sample_rate=44100 and a positive segment_seconds")
        if self.crops_per_track <= 0 or not 0 <= self.remix_prob <= 1 or self.gain_db < 0:
            raise ValueError("Invalid crops_per_track, validation_crops, remix_prob, or gain_db")
        if len(set(self.sources)) != len(self.sources) or set(self.sources) != set(DEFAULT_SOURCES):
            raise ValueError("sources must contain vocals, drums, bass, other exactly once")
        seen = set()
        for record in self.records:
            if training and record["subset"] != "train":
                raise ValueError(f"Training dataset includes {record['subset']} song: {record['track_name']}")
            identity = record["track_name"]
            if identity in seen:
                raise ValueError(f"Duplicate track: {identity}")
            seen.add(identity)
            if record["sample_rate"] != sample_rate or record["channels"] != 2 or record["frames"] <= 0:
                raise ValueError(f"Invalid manifest metadata for {identity}")
            for name in _ALL_FILES:
                info = sf.info(Path(record["path"]) / f"{name}.wav")
                if (info.samplerate, info.channels, info.frames) != (sample_rate, 2, record["frames"]):
                    raise ValueError(f"WAV/manifest mismatch for {identity}/{name}.wav; rescan the dataset")

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __len__(self) -> int:
        return len(self.records) * self.crops_per_track

    def _read(self, record: dict, source: str, start: int) -> np.ndarray:
        frames = min(self.segment_frames, record["frames"] - start)
        audio, sr = sf.read(Path(record["path"]) / f"{source}.wav", start=start, frames=frames,
                            dtype="float32", always_2d=True)
        if sr != self.sample_rate or audio.shape != (frames, 2) or not np.isfinite(audio).all():
            raise ValueError(f"Invalid audio crop: {record['track_name']}/{source}.wav at {start}")
        result = np.zeros((2, self.segment_frames), dtype=np.float32)
        result[:, :frames] = audio.T
        return result

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        if not 0 <= index < len(self):
            raise IndexError(index)
        record = self.records[index // self.crops_per_track]
        last_start = max(0, record["frames"] - self.segment_frames)
        if self.training:
            rng = np.random.default_rng(np.random.SeedSequence((self.seed, self.epoch, index)))
            start = int(rng.integers(last_start + 1))
            remix = rng.random() < self.remix_prob
            targets = []
            for source in self.sources:
                source_record = self.records[int(rng.integers(len(self.records)))] if remix else record
                source_start = int(rng.integers(max(0, source_record["frames"] - self.segment_frames) + 1)) if remix else start
                stem = self._read(source_record, source, source_start)
                stem *= np.float32(10 ** (rng.uniform(-self.gain_db, self.gain_db) / 20))
                if rng.random() < 0.5:
                    stem *= -1
                if rng.random() < 0.5:
                    stem = stem[::-1].copy()
                targets.append(stem)
            targets = np.stack(targets)
            mixture = targets.sum(axis=0)
        else:
            crop_index = index % self.crops_per_track
            fraction = 0.5 if self.crops_per_track == 1 else crop_index / (self.crops_per_track - 1)
            start = round(last_start * fraction)
            targets = np.stack([self._read(record, source, start) for source in self.sources])
            mixture = self._read(record, "mixture", start)
        peak = max(float(np.max(np.abs(mixture))), float(np.max(np.abs(targets))))
        if peak > 1.0:
            scale = np.float32(0.99 / peak)
            targets *= scale
            if self.training:
                # Re-summing preserves exact mixture consistency after rounding.
                mixture = targets.sum(axis=0)
            else:
                mixture *= scale
        target_tensor = torch.from_numpy(targets.copy())
        mixture_tensor = target_tensor.sum(dim=0) if self.training else torch.from_numpy(mixture.copy())
        return mixture_tensor, target_tensor


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit local MUSDB18-HQ WAVs and write a manifest")
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--no-strict", action="store_true", help="Allow a partial dataset; keep WAV checks")
    parser.add_argument("--probe-seconds", type=float, default=1.0)
    parser.add_argument("--reject-known-errata", action="store_true",
                        help="Reject residual mismatch on either channel of test/PR - Oh No as well")
    args = parser.parse_args()
    records = scan_dataset(args.root, args.output, strict=not args.no_strict, probe_seconds=args.probe_seconds,
                           allow_known_errata=not args.reject_known_errata)
    counts = {subset: sum(record["subset"] == subset for record in records) for subset in ("train", "val", "test")}
    print(json.dumps({"manifest": str(args.output), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
