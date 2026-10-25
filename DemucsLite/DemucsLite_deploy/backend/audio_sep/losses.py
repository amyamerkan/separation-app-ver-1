"""Balanced waveform and stereo spectral objectives with explicit silence handling.

Unlike a global L1, each item/stem is normalized independently, preventing loud
drums from dominating quiet vocals. The mixture RMS floor limits amplification
of nearly silent labels. No residual-correlation heuristic is used: correlated
instruments are legitimate, and penalizing them is not proof of less leakage.
"""

from __future__ import annotations

from typing import Sequence

import torch
from torch import Tensor

from .metrics import _check_pair, si_sdr_values


def _source_scales(target: Tensor, mixture: Tensor, eps: float = 1e-4) -> Tensor:
    source_rms = target.square().mean(dim=(-2, -1)).clamp_min(eps**2).sqrt()
    mixture_rms = mixture.square().mean(dim=(-2, -1)).clamp_min(eps**2).sqrt()
    return torch.maximum(source_rms, 0.1 * mixture_rms[:, None]).clamp_min(eps)


def multi_resolution_stft_loss(estimate: Tensor, target: Tensor,
                               mixture: Tensor | None = None,
                               fft_sizes: Sequence[int] = (512, 1024, 2048, 4096)) -> Tensor:
    """Equal item/stem weighting; preserve L/R instead of averaging to mono.

    Spectral convergence is undefined for a silent target, so those entries use
    only log-magnitude error. Waveform/silence loss still penalizes hallucinations.
    Constant padding supports clips shorter than half an FFT window.
    """
    _check_pair(estimate, target)
    if not fft_sizes or any(size < 4 for size in fft_sizes):
        raise ValueError("fft_sizes must contain integers >= 4")
    with torch.autocast(device_type=estimate.device.type, enabled=False):
        estimate, target = estimate.float(), target.float()
        if mixture is None:
            mixture = target.sum(dim=1)
        mixture = mixture.float()
        scales = _source_scales(target, mixture)
        batch, sources, channels, samples = target.shape
        active = target.square().mean(dim=(-2, -1)) > 1e-6
        estimate = (estimate / scales[:, :, None, None]).reshape(-1, samples)
        target = (target / scales[:, :, None, None]).reshape(-1, samples)
        total = estimate.new_zeros(())
        for size in fft_sizes:
            window = torch.hann_window(size, device=estimate.device, dtype=torch.float32)
            est_mag = torch.stft(estimate, size, hop_length=size // 4, window=window,
                                 return_complex=True, center=True, pad_mode="constant").abs()
            tgt_mag = torch.stft(target, size, hop_length=size // 4, window=window,
                                 return_complex=True, center=True, pad_mode="constant").abs()
            est_mag = est_mag.reshape(batch, sources, channels, *est_mag.shape[-2:])
            tgt_mag = tgt_mag.reshape(batch, sources, channels, *tgt_mag.shape[-2:])
            diff_norm = torch.linalg.vector_norm((est_mag - tgt_mag).flatten(start_dim=2), dim=-1)
            target_norm = torch.linalg.vector_norm(tgt_mag.flatten(start_dim=2), dim=-1).clamp_min(1e-4)
            convergence = torch.where(active, diff_norm / target_norm, torch.zeros_like(diff_norm))
            log_magnitude = (torch.log1p(est_mag) - torch.log1p(tgt_mag)).abs().mean(dim=(-3, -2, -1))
            total = total + (convergence + log_magnitude).mean()
        return total / len(fft_sizes)


def si_sdr_loss(estimate: Tensor, target: Tensor, silence_threshold_db: float = -60.0) -> Tensor:
    """Negative active-stem SI-SDR, clipped to [-30,30] dB for stability."""
    _check_pair(estimate, target)
    with torch.autocast(device_type=estimate.device.type, enabled=False):
        active = target.float().square().mean(dim=(-2, -1)) > 10.0 ** (silence_threshold_db / 10.0)
        values = si_sdr_values(estimate, target).clamp(-30.0, 30.0)
        # Tensor-only aggregation keeps the all-silent result attached to autograd.
        return -(values * active).sum() / active.sum().clamp_min(1)


def separation_loss(estimate: Tensor, target: Tensor, mixture: Tensor,
                    spectral_weight: float = 0.05, si_sdr_weight: float = 0.01,
                    consistency_weight: float = 0.1,
                    fft_sizes: Sequence[int] = (512, 1024, 2048, 4096)) -> tuple[Tensor, dict[str, Tensor]]:
    """Return the scalar objective and detached component values for logging.

    All waveforms are unnormalized floating-point amplitudes. Supply the actual
    augmented mixture corresponding to ``target``. Weights are starting points,
    to be selected on a fixed validation set rather than called universally best.
    """
    _check_pair(estimate, target)
    if mixture.shape != (target.shape[0], target.shape[2], target.shape[3]):
        raise ValueError("mixture must have [batch, channel, samples] matching the targets")
    if min(spectral_weight, si_sdr_weight, consistency_weight) < 0:
        raise ValueError("loss weights must be nonnegative")
    with torch.autocast(device_type=estimate.device.type, enabled=False):
        estimate, target, mixture = estimate.float(), target.float(), mixture.float()
        scales = _source_scales(target, mixture)
        source_l1 = ((estimate - target).abs().mean(dim=(-2, -1)) / scales).mean()
        mixture_scale = mixture.square().mean(dim=(-2, -1)).clamp_min(1e-8).sqrt()
        mixture_l1 = ((estimate.sum(dim=1) - mixture).abs().mean(dim=(-2, -1)) / mixture_scale).mean()
        inactive = target.square().mean(dim=(-2, -1)) <= 1e-6
        silence_per_source = estimate.abs().mean(dim=(-2, -1)) / scales
        silence = (silence_per_source * inactive).sum() / inactive.sum().clamp_min(1)
        zero = source_l1 * 0
        spectral = multi_resolution_stft_loss(estimate, target, mixture, fft_sizes) if spectral_weight else zero
        si_sdr = si_sdr_loss(estimate, target) if si_sdr_weight else zero
        total = (source_l1 + consistency_weight * mixture_l1 + spectral_weight * spectral
                 + si_sdr_weight * (si_sdr + silence))
        parts = {"source_l1": source_l1, "mixture_l1": mixture_l1,
                 "spectral": spectral, "si_sdr": si_sdr, "silence": silence}
        return total, {name: value.detach() for name, value in parts.items()}
