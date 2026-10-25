"""
Kiến trúc mạng U-Net cơ sở dựa trên Demucs (tinh gọn)
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


class EncoderBlock(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride):
        super().__init__()
        self.conv = nn.Conv1d(in_channels, out_channels, kernel_size, stride)
        self.glu_conv = nn.Conv1d(out_channels, 2 * out_channels, kernel_size=1)

    def forward(self, x):
        x = F.relu(self.conv(x))
        x = self.glu_conv(x)
        x = F.glu(x, dim=1)
        return x


class DecoderBlock(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride, is_last=False):
        super().__init__()
        self.glu_conv = nn.Conv1d(in_channels, 2 * in_channels, kernel_size=3, padding=1)
        self.deconv = nn.ConvTranspose1d(in_channels, out_channels, kernel_size, stride)
        self.is_last = is_last

    def forward(self, x, skip):
        x = x + skip
        x = self.glu_conv(x)
        x = F.glu(x, dim=1)
        x = self.deconv(x)
        if not self.is_last:
            x = F.relu(x)
        return x


class DemucsLite(nn.Module):
    def __init__(
        self,
        sources=4,
        audio_channels=2,
        channels=32,
        depth=5,
        growth=2,
        kernel_size=8,
        stride=4,
        lstm_layers=1,
    ):
        super().__init__()
        self.sources = sources
        self.audio_channels = audio_channels
        self.kernel_size = kernel_size
        self.stride = stride
        self.depth = depth

        self.encoders = nn.ModuleList()
        self.decoders = nn.ModuleList()

        in_ch = audio_channels
        out_ch = channels
        channel_sizes = []
        for i in range(depth):
            self.encoders.append(EncoderBlock(in_ch, out_ch, kernel_size, stride))
            channel_sizes.append(out_ch)
            in_ch = out_ch
            out_ch = int(out_ch * growth)

        bottleneck_ch = channel_sizes[-1]
        self.lstm = nn.LSTM(
            input_size=bottleneck_ch,
            hidden_size=bottleneck_ch,
            num_layers=lstm_layers,
            bidirectional=True,
            batch_first=True,
        )
        self.lstm_proj = nn.Linear(2 * bottleneck_ch, bottleneck_ch)

        rev_channels = list(reversed(channel_sizes))
        for i in range(depth):
            in_ch = rev_channels[i]
            if i + 1 < depth:
                out_ch = rev_channels[i + 1]
            else:
                out_ch = sources * audio_channels
            is_last = i == depth - 1
            self.decoders.append(DecoderBlock(in_ch, out_ch, kernel_size, stride, is_last))

    def valid_length(self, length):
        for _ in range(self.depth):
            length = math.ceil((length - self.kernel_size) / self.stride) + 1
            length = max(length, 1)
        for _ in range(self.depth):
            length = (length - 1) * self.stride + self.kernel_size
        return int(length)

    def forward(self, mixture):
        original_length = mixture.shape[-1]
        target_length = self.valid_length(original_length)
        pad_amount = target_length - original_length
        x = F.pad(mixture, (0, pad_amount))

        skips = []
        for enc in self.encoders:
            x = enc(x)
            skips.append(x)

        x_lstm = x.permute(0, 2, 1)
        x_lstm, _ = self.lstm(x_lstm)
        x_lstm = self.lstm_proj(x_lstm)
        x = x_lstm.permute(0, 2, 1)

        for dec, skip in zip(self.decoders, reversed(skips)):
            x = dec(x, skip)

        x = x[..., :original_length]
        batch = x.shape[0]
        x = x.view(batch, self.sources, self.audio_channels, -1)
        return x


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)