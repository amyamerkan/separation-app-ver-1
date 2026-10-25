import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch import nn

from audio_sep.data import DEFAULT_SOURCES
from audio_sep.inference import load_audio, load_checkpoint, overlap_add, save_stems
from audio_sep.model import DemucsLiteV2


class Splitter(nn.Module):
    sources = DEFAULT_SOURCES
    samplerate = 100

    def forward(self, mix):
        return mix[:, None].repeat(1, 4, 1, 1) / 4


class InferenceTest(unittest.TestCase):
    def test_overlap_boundaries_and_reconstruction(self):
        for length in (1, 7, 99, 513):
            x = torch.randn(2, length)
            y = overlap_add(Splitter(), x, segment_seconds=1)
            self.assertEqual(y.shape, (4, 2, length))
            torch.testing.assert_close(y.sum(0), x)

    def test_float_export_does_not_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            x = torch.full((4, 2, 21), 1.5)
            save_stems(x, temp)
            y, _ = sf.read(Path(temp) / "vocals.wav")
            np.testing.assert_allclose(y, 1.5)

    def test_mono_becomes_stereo_and_bad_audio_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.wav"
            sf.write(path, np.ones(20), 44100, subtype="FLOAT")
            y = load_audio(path)
            self.assertEqual(tuple(y.shape), (2, 20))
            torch.testing.assert_close(y[0], y[1])
            sf.write(path, np.full(20, np.nan), 44100, subtype="FLOAT")
            with self.assertRaises(ValueError):
                load_audio(path)

    def test_checkpoint_honors_selected_raw_weights(self):
        model = DemucsLiteV2(channels=4, depth=2, lstm_layers=1)
        raw = model.state_dict()
        ema = {k: v + 1 if v.is_floating_point() else v for k, v in raw.items()}
        checkpoint = {"format_version": 2, "model_kind": "lite", "model_config": model.export_config(),
                      "model_state_dict": raw, "ema_state_dict": ema, "selected_weights": "raw"}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "best.pth"
            torch.save(checkpoint, path)
            loaded, _ = load_checkpoint(path)
            for key, value in loaded.state_dict().items():
                torch.testing.assert_close(value, raw[key])


if __name__ == "__main__":
    unittest.main()
