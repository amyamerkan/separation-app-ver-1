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


class LowFreqResidual2D(nn.Module):
    """Frequency-asymmetric dilated depthwise-separable 2D residual block."""

    def __init__(self, channels: int, freq_dilation: int = 1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(
                channels, channels, kernel_size=(5, 3),
                padding=(2 * freq_dilation, 1), dilation=(freq_dilation, 1),
                groups=channels,
            ),
            nn.GroupNorm(1, channels),
            nn.GELU(),
            nn.Conv2d(channels, 2 * channels, kernel_size=1),
            nn.GLU(dim=1),
        )
        self.scale = nn.Parameter(torch.full((1, channels, 1, 1), 1e-3))

    def forward(self, x: Tensor) -> Tensor:
        return x + self.scale * self.block(x)


class LowFreqSpecialistCNN(nn.Module):
    """
    Multi-Scale Spectral 2D-CNN operating on STFT bins [0, low_bins).
    Combines 4x frequency encoder-decoder context with Complex Ratio Masking (CRM)
    and fine complex residual refinement to isolate vocals from overlapping accompaniment.
    """

    def __init__(
        self,
        sources: int,
        audio_channels: int = 2,
        n_fft: int = 4096,
        hop_length: int = 1024,
        low_bins: int = 1024,
        hidden_channels: int = 64,
        depth: int = 4,
    ):
        super().__init__()
        self.sources = sources
        self.audio_channels = audio_channels
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.max_bins = n_fft // 2 + 1
        self.low_bins = min(low_bins, self.max_bins)
        in_ch = audio_channels * 2
        out_ch = sources * audio_channels * 2

        self.stem = nn.Sequential(
            nn.Conv2d(in_ch, hidden_channels, kernel_size=3, padding=1),
            nn.GroupNorm(1, hidden_channels),
            nn.GELU(),
        )
        self.freq_down = nn.Sequential(
            nn.Conv2d(hidden_channels, hidden_channels, kernel_size=(4, 3), stride=(2, 1), padding=(1, 1)),
            nn.GroupNorm(1, hidden_channels),
            nn.GELU(),
            nn.Conv2d(hidden_channels, hidden_channels, kernel_size=(4, 3), stride=(2, 1), padding=(1, 1)),
            nn.GroupNorm(1, hidden_channels),
            nn.GELU(),
        )
        self.freq_bottleneck = LowFreqResidual2D(hidden_channels, freq_dilation=2)
        self.freq_up = nn.Sequential(
            nn.ConvTranspose2d(hidden_channels, hidden_channels, kernel_size=(4, 3), stride=(2, 1), padding=(1, 1)),
            nn.GroupNorm(1, hidden_channels),
            nn.GELU(),
            nn.ConvTranspose2d(hidden_channels, hidden_channels, kernel_size=(4, 3), stride=(2, 1), padding=(1, 1)),
            nn.GroupNorm(1, hidden_channels),
            nn.GELU(),
        )
        self.blocks = nn.ModuleList([
            LowFreqResidual2D(hidden_channels, freq_dilation=2**i)
            for i in range(depth)
        ])
        self.mask_head = nn.Conv2d(hidden_channels, out_ch, kernel_size=1)
        self.res_head = nn.Conv2d(hidden_channels, out_ch, kernel_size=1)
        self.register_buffer("window", torch.hann_window(n_fft), persistent=False)

    def forward(self, x: Tensor) -> Tensor:
        batch, channels, length = x.shape
        pad_right = max(0, self.n_fft - length)
        x_padded = F.pad(x, (0, pad_right)) if pad_right > 0 else x
        padded_len = x_padded.shape[-1]

        with torch.autocast(device_type=x.device.type, enabled=False):
            x_f32 = x_padded.float().reshape(batch * channels, padded_len)
            win = self.window.to(device=x.device, dtype=torch.float32)
            spec = torch.stft(
                x_f32, n_fft=self.n_fft, hop_length=self.hop_length,
                win_length=self.n_fft, window=win,
                center=True, pad_mode="constant", return_complex=True,
            )
            _, total_bins, frames = spec.shape
            spec_low = spec[:, :self.low_bins, :]
            f_pad = (4 - (self.low_bins % 4)) % 4
            feat = (
                torch.view_as_real(spec_low)
                .permute(0, 3, 1, 2)
                .reshape(batch, channels * 2, self.low_bins, frames)
            )
            if f_pad:
                feat = F.pad(feat, (0, 0, 0, f_pad))

            h = self.stem(feat)
            h_ms = self.freq_up(self.freq_bottleneck(self.freq_down(h)))[..., :h.shape[-2], :h.shape[-1]]
            h = h + 0.5 * h_ms
            for block in self.blocks:
                h = block(h)
            if f_pad:
                h = h[:, :, :self.low_bins, :]

            crm = torch.tanh(self.mask_head(h)) * 1.5
            res = self.res_head(h) * 0.2

            crm = crm.reshape(batch, self.sources, channels, 2, self.low_bins, frames).permute(0, 1, 2, 4, 5, 3).contiguous()
            res = res.reshape(batch, self.sources, channels, 2, self.low_bins, frames).permute(0, 1, 2, 4, 5, 3).contiguous()
            crm_c = torch.view_as_complex(crm)
            res_c = torch.view_as_complex(res)

            mix_low_c = spec_low.reshape(batch, 1, channels, self.low_bins, frames)
            delta_complex = (crm_c * mix_low_c + res_c).reshape(batch * self.sources * channels, self.low_bins, frames)

            full_spec = delta_complex.new_zeros((batch * self.sources * channels, total_bins, frames))
            full_spec[:, :self.low_bins, :] = delta_complex

            wav_delta = torch.istft(
                full_spec, n_fft=self.n_fft, hop_length=self.hop_length,
                win_length=self.n_fft, window=win,
                center=True, length=padded_len,
            )
            wav_delta = wav_delta.reshape(batch, self.sources, channels, padded_len)[..., :length]
        return wav_delta.to(dtype=x.dtype)


class DemucsLiteV2(nn.Module):
    """Predict named stereo stems with the same number of samples as the input."""

    def __init__(
        self,
        sources: Sequence[str] = DEFAULT_SOURCES,
        audio_channels: int = 2,
        sample_rate: int = 44100,
        channels: int = 64,
        depth: int = 5,
        growth: float = 2.0,
        max_channels: int = 768,
        kernel_size: int = 8,
        stride: int = 4,
        lstm_layers: int = 2,
        dconv_depth: int = 3,
        normalize: bool = True,
        mixture_consistency: bool = True,
        low_freq_cnn: bool = True,
        stft_n_fft: int = 4096,
        stft_hop: int = 1024,
        low_bins: int = 1024,
        lf_channels: int = 64,
        lf_depth: int = 4,
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
        self.low_freq_cnn = bool(low_freq_cnn)
        self.stft_n_fft = int(stft_n_fft)
        self.stft_hop = int(stft_hop)
        self.low_bins = int(low_bins)
        self.lf_channels = int(lf_channels)
        self.lf_depth = int(lf_depth)

        channel_sizes = [min(max_channels, int(channels * growth**index)) for index in range(depth)]
        self.encoders = nn.ModuleList()
        input_channels = audio_channels
        for index, output_channels in enumerate(channel_sizes):
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

        if self.low_freq_cnn:
            self.lf_branch = LowFreqSpecialistCNN(
                sources=len(self.sources),
                audio_channels=audio_channels,
                n_fft=self.stft_n_fft,
                hop_length=self.stft_hop,
                low_bins=self.low_bins,
                hidden_channels=self.lf_channels,
                depth=self.lf_depth,
            )
            self.lf_gate = nn.Parameter(torch.full((1, len(self.sources), 1, 1), 0.25))
        else:
            self.lf_branch = None
            self.lf_gate = None

    def export_config(self) -> dict:
        return {
            "sources": list(self.sources), "audio_channels": self.audio_channels,
            "sample_rate": self.sample_rate, "channels": self.channels, "depth": self.depth,
            "growth": self.growth, "max_channels": self.max_channels,
            "kernel_size": self.kernel_size, "stride": self.stride,
            "lstm_layers": self.lstm_layers, "dconv_depth": self.dconv_depth,
            "normalize": self.normalize, "mixture_consistency": self.mixture_consistency,
            "low_freq_cnn": self.low_freq_cnn, "stft_n_fft": self.stft_n_fft,
            "stft_hop": self.stft_hop, "low_bins": self.low_bins,
            "lf_channels": self.lf_channels, "lf_depth": self.lf_depth,
        }

    @property
    def samplerate(self) -> int:
        return self.sample_rate

    def valid_length(self, length: int) -> int:
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
            x_norm = centered / scale
        else:
            mean = mixture.new_zeros((mixture.shape[0], 1, 1))
            scale = mixture.new_ones((mixture.shape[0], 1, 1))
            x_norm = mixture
        left_padding = (padded_length - original_length) // 2
        right_padding = padded_length - original_length - left_padding
        x = F.pad(x_norm, (left_padding, right_padding))
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
        if self.lf_branch is not None:
            x = x + self.lf_gate * self.lf_branch(x_norm)
        x = x * scale[:, None] + mean[:, None] / len(self.sources)
        if self.mixture_consistency:
            # Energy-Weighted Consistency: phân bổ phần dư theo năng lượng từng nguồn (không đẩy nhạc nền vào khoảng lặng của Vocals)
            energy = x.square().mean(dim=(-2, -1), keepdim=True) + 1e-6
            weights = energy / energy.sum(dim=1, keepdim=True)
            x = x + weights * (mixture[:, None] - x.sum(dim=1, keepdim=True))
        return x


def count_parameters(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)