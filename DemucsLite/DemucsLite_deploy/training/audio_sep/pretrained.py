"""Train one HTDemucs backbone, preserving its source order and context length."""
import torch
from torch import nn
from torch.nn import functional as F

from .data import DEFAULT_SOURCES


class PretrainedSeparator(nn.Module):
    def __init__(self, name="htdemucs", sources=DEFAULT_SOURCES, segment=None,
                 init_args=None, init_kwargs=None):
        super().__init__()
        if init_args is not None and init_kwargs is not None:
            from demucs.htdemucs import HTDemucs
            backbone = HTDemucs(*init_args, **init_kwargs)
        else:
            from .compat import official_model
            backbone = official_model(name)
        if hasattr(backbone, "models"):
            if len(backbone.models) != 1:
                raise ValueError("Fine-tune one htdemucs backbone; use htdemucs_ft for inference.")
            backbone = backbone.models[0]
        self.backbone = backbone
        self.name = name
        self.sources = tuple(sources)
        if set(self.sources) != set(backbone.sources):
            raise ValueError("Source names do not match pretrained backbone.")
        self.audio_channels = backbone.audio_channels
        self.samplerate = backbone.samplerate
        self.segment = float(backbone.segment if segment is None else segment)
        self.backbone.segment = self.segment
        self.order = [backbone.sources.index(s) for s in self.sources]

    def forward(self, mixture):
        length = mixture.shape[-1]
        context = round(self.segment * self.samplerate)
        if length > context:
            raise ValueError("Input exceeds HTDemucs training context; use split inference.")
        # Official Demucs input conditioning; one shared transform for every stem.
        reference = mixture.mean(dim=1, keepdim=True)
        mean = reference.mean(dim=-1, keepdim=True)
        std = reference.std(dim=-1, keepdim=True, unbiased=False).clamp_min(1e-5)
        x = F.pad((mixture - mean) / std, (0, context - length))
        # HTDemucs.forward mutates segment in train mode. Keep the original context.
        y = self.backbone(x)[:, self.order, ..., :length]
        self.backbone.segment = self.segment
        return y * std[:, None] + mean[:, None] / len(self.sources)

    def export_config(self):
        args, kwargs = self.backbone._init_args_kwargs
        return {"name": self.name, "sources": list(self.sources), "segment": self.segment,
                "init_args": args, "init_kwargs": kwargs}
