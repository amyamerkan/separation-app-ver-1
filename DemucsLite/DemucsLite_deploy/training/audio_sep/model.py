"""A stereo waveform U-Net intended for training a compact separator from scratch.

This is a new architecture: original ``DemucsLite`` checkpoints are not compatible.
It does not contain pretrained weights and does not promise state-of-the-art quality.
"""

from __future__ import annotations

import math
from typing import Sequence

import torch
from torch import Tensor, nn
from torch.nn import functional as F


DEFAULT_SOURCES = ("vocals", "drums", "bass", "other")


class ResidualDConv(nn.Module):
    """Compressed, dilated residual convolutions without batch statistics."""

    def __init__(self, channels: int, depth: int = 2, compression: int = 4):
        super().__init__()
        hidden = max(8, channels // compression)
        self.blocks = nn.ModuleList()
        self.scales = nn.ParameterList()
        for index in range(depth):
            dilation = 2**index
            self.blocks.append(
                nn.Sequential(
                    nn.Conv1d(channels, hidden, kernel_size=1),
                    # One group also works for batch=1 and a single bottleneck frame.
                    nn.GroupNorm(1, hidden),
                    nn.GELU(),
                    nn.Conv1d(hidden, hidden, 3, padding=dilation, dilation=dilation),
                    nn.GroupNorm(1, hidden),
                    nn.GELU(),
                    nn.Conv1d(hidden, 2 * channels, kernel_size=1),
                    nn.GLU(dim=1),
                )
            )
            self.scales.append(nn.Parameter(torch.full((1, channels, 1), 1e-3)))

    def forward(self, x: Tensor) -> Tensor:
        for block, scale in zip(self.blocks, self.scales):
            x = x + scale * block(x)
        return x


class EncoderBlock(nn.Module):
    def __init__(self, input_channels: int, output_channels: int,
                 kernel_size: int, stride: int, dconv_depth: int):
        super().__init__()
        self.conv = nn.Conv1d(input_channels, output_channels, kernel_size, stride)
        self.context = ResidualDConv(output_channels, dconv_depth)
        self.gate = nn.Conv1d(output_channels, 2 * output_channels, 1)

    def forward(self, x: Tensor) -> Tensor:
        x = F.gelu(self.conv(x))
        return F.glu(self.gate(self.context(x)), dim=1)


class DecoderBlock(nn.Module):
    def __init__(self, input_channels: int, output_channels: int,
                 kernel_size: int, stride: int, dconv_depth: int, last: bool):
        super().__init__()
        self.context = ResidualDConv(input_channels, dconv_depth)
        self.gate = nn.Conv1d(input_channels, 2 * input_channels, 3, padding=1)
        self.upsample = nn.ConvTranspose1d(input_channels, output_channels, kernel_size, stride)
        self.last = last

    def forward(self, x: Tensor, skip: Tensor) -> Tensor:
        x = (x + skip) * (2.0**-0.5)
        x = F.glu(self.gate(self.context(x)), dim=1)
        x = self.upsample(x)
        return x if self.last else F.gelu(x)


class DemucsLiteV2(nn.Module):
    """Predict named stereo stems with the same number of samples as the input.

    Input: ``[batch, audio_channels, samples]``. Output:
    ``[batch, len(sources), audio_channels, samples]`` in ``sources`` order.
    Normalization uses one shared mean/scale per mixture, preserving stereo gains.
    Optional mixture consistency distributes the remaining residual equally. Leave
    it disabled when measuring whether the model learned to reconstruct mixtures.
    ``lstm_layers=0`` disables the recurrent bottleneck for a cheaper deployment.
    """

    def __init__(
        self,
        sources: Sequence[str] = DEFAULT_SOURCES,
        audio_channels: int = 2,
        sample_rate: int = 44100,
        channels: int = 32,
        depth: int = 5,
        growth: float = 2.0,
        max_channels: int = 512,
        kernel_size: int = 8,
        stride: int = 4,
        lstm_layers: int = 2,
        dconv_depth: int = 2,
        normalize: bool = True,
        mixture_consistency: bool = False,
    ):
        super().__init__()
        if isinstance(sources, (str, int)) or not sources:
            raise ValueError("sources must be a nonempty sequence of unique stem names")
        self.sources = tuple(sources)
        if len(set(self.sources)) != len(self.sources) or not all(isinstance(s, str) for s in self.sources):
            raise ValueError("sources must contain unique strings")
        if min(audio_channels, sample_rate, channels, depth, max_channels, kernel_size, stride) < 1:
            raise ValueError("channel counts, depth, sample rate, kernel and stride must be positive")
        if kernel_size < stride or growth < 1 or lstm_layers < 0 or dconv_depth < 0:
            raise ValueError("require kernel_size >= stride, growth >= 1 and nonnegative block depths")
        self.audio_channels = audio_channels
        self.sample_rate = sample_rate
        self.channels = channels
        self.depth = depth
        self.growth = growth
        self.max_channels = max_channels
        self.kernel_size = kernel_size
        self.stride = stride
        self.lstm_layers = lstm_layers
        self.dconv_depth = dconv_depth
        self.normalize = normalize
        self.mixture_consistency = mixture_consistency

        channel_sizes = [min(max_channels, int(channels * growth**index)) for index in range(depth)]
        self.encoders = nn.ModuleList()
        input_channels = audio_channels
        for index, output_channels in enumerate(channel_sizes):
            # Avoid costly context convolutions on the longest, shallow features.
            block_depth = dconv_depth if index >= 2 else 0
            self.encoders.append(EncoderBlock(input_channels, output_channels, kernel_size, stride, block_depth))
            input_channels = output_channels

        bottleneck_channels = channel_sizes[-1]
        if lstm_layers:
            hidden = max(1, bottleneck_channels // 2)
            self.lstm = nn.LSTM(bottleneck_channels, hidden, num_layers=lstm_layers,
                                bidirectional=True, batch_first=True)
            self.lstm_projection = nn.Linear(2 * hidden, bottleneck_channels)
        else:
            self.lstm = None
            self.lstm_projection = None

        self.decoders = nn.ModuleList()
        for index in reversed(range(depth)):
            output_channels = channel_sizes[index - 1] if index else len(self.sources) * audio_channels
            self.decoders.append(DecoderBlock(channel_sizes[index], output_channels, kernel_size,
                                              stride, dconv_depth if index >= 2 else 0, index == 0))

    def export_config(self) -> dict:
        """JSON-compatible configuration, including the exact stem order."""
        return {
            "sources": list(self.sources), "audio_channels": self.audio_channels,
            "sample_rate": self.sample_rate, "channels": self.channels, "depth": self.depth,
            "growth": self.growth, "max_channels": self.max_channels,
            "kernel_size": self.kernel_size, "stride": self.stride,
            "lstm_layers": self.lstm_layers, "dconv_depth": self.dconv_depth,
            "normalize": self.normalize, "mixture_consistency": self.mixture_consistency,
        }

    @property
    def samplerate(self) -> int:
        """Match the metadata name used by official Demucs inference utilities."""
        return self.sample_rate

    def valid_length(self, length: int) -> int:
        """Next input length that all valid strided convolutions reconstruct."""
        if length < 1:
            raise ValueError("audio must contain at least one sample")
        for _ in range(self.depth):
            length = max(1, math.ceil((length - self.kernel_size) / self.stride) + 1)
        for _ in range(self.depth):
            length = (length - 1) * self.stride + self.kernel_size
        return int(length)

    def forward(self, mixture: Tensor) -> Tensor:
        if mixture.ndim != 3 or mixture.shape[1] != self.audio_channels:
            raise ValueError(f"expected [batch, {self.audio_channels}, samples], got {tuple(mixture.shape)}")
        original_length = mixture.shape[-1]
        padded_length = self.valid_length(original_length)
        if self.normalize:
            mean = mixture.mean(dim=(1, 2), keepdim=True)
            centered = mixture - mean
            scale = centered.square().mean(dim=(1, 2), keepdim=True).clamp_min(1e-6).sqrt()
            x = centered / scale
        else:
            mean = mixture.new_zeros((mixture.shape[0], 1, 1))
            scale = mixture.new_ones((mixture.shape[0], 1, 1))
            x = mixture
        left_padding = (padded_length - original_length) // 2
        right_padding = padded_length - original_length - left_padding
        x = F.pad(x, (left_padding, right_padding))
        skips = []
        for encoder in self.encoders:
            x = encoder(x)
            skips.append(x)
        if self.lstm is not None:
            x, _ = self.lstm(x.transpose(1, 2))
            x = self.lstm_projection(x).transpose(1, 2)
        for decoder, skip in zip(self.decoders, reversed(skips)):
            x = decoder(x, skip)
        x = x[..., left_padding:left_padding + original_length]
        x = x.reshape(mixture.shape[0], len(self.sources), self.audio_channels, original_length)
        # Adding the mixture mean to every stem would multiply its DC by S.
        x = x * scale[:, None] + mean[:, None] / len(self.sources)
        if self.mixture_consistency:
            x = x + (mixture - x.sum(dim=1))[:, None] / len(self.sources)
        return x


def count_parameters(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
