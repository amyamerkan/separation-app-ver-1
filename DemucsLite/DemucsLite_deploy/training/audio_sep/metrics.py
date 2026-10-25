"""Small, transparent metrics; these are not the official MUSDB BSS Eval SDR.

SNR here is 10*log10(target energy / reconstruction error energy). SI-SDR uses
one common scale for the stereo pair after removing each channel's temporal mean.
All results have shape [batch, source]. Exclude entries with ``active=False``
from reported means; their dB values are zero placeholders, not measurements.
"""

from __future__ import annotations

import torch
from torch import Tensor


def _check_pair(estimate: Tensor, target: Tensor) -> None:
    if estimate.ndim != 4 or estimate.shape != target.shape or estimate.shape[-1] < 1:
        raise ValueError("estimate and target must have equal [batch, source, channel, samples] shapes")


def si_sdr_values(estimate: Tensor, target: Tensor, eps: float = 1e-8) -> Tensor:
    """Stereo SI-SDR [B,S], with float32 arithmetic and bounded numerical floors."""
    _check_pair(estimate, target)
    estimate = estimate.float()
    target = target.float()
    estimate = (estimate - estimate.mean(dim=-1, keepdim=True)).flatten(start_dim=2)
    target = (target - target.mean(dim=-1, keepdim=True)).flatten(start_dim=2)
    target_power = target.square().mean(dim=-1, keepdim=True)
    gain = (estimate * target).mean(dim=-1, keepdim=True) / target_power.clamp_min(eps)
    projected = gain * target
    residual = estimate - projected
    projection_power = projected.square().mean(dim=-1)
    residual_power = residual.square().mean(dim=-1)
    return 10.0 * torch.log10((projection_power + eps) / (residual_power + eps))


def metrics_per_source(estimate: Tensor, target: Tensor,
                       silence_threshold_db: float = -60.0) -> dict[str, Tensor]:
    """Return metrics in the tensor/model source order, including silence leakage.

    ``silent_estimate_energy`` is linear mean-square amplitude on inactive stems
    and zero on active ones. Report its mean only over inactive entries.
    Silence threshold is power in dBFS; -60 corresponds to an RMS of 0.001.
    """
    _check_pair(estimate, target)
    with torch.autocast(device_type=estimate.device.type, enabled=False):
        estimate, target = estimate.float(), target.float()
        power = target.square().mean(dim=(-2, -1))
        active = power > 10.0 ** (silence_threshold_db / 10.0)
        error_power = (estimate - target).square().mean(dim=(-2, -1))
        snr = 10.0 * torch.log10((power + 1e-8) / (error_power + 1e-8))
        si_sdr = si_sdr_values(estimate, target)
        estimate_power = estimate.square().mean(dim=(-2, -1))
        return {
            "snr_db": torch.where(active, snr, torch.zeros_like(snr)),
            "si_sdr_db": torch.where(active, si_sdr, torch.zeros_like(si_sdr)),
            "active": active,
            "silent_estimate_energy": torch.where(active, torch.zeros_like(estimate_power), estimate_power),
        }
