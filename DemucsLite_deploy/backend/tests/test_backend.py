"""Deployment contract tests. Tiny test models verify plumbing, not audio quality."""
import io
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import numpy as np
import soundfile as sf
import torch
from fastapi.testclient import TestClient
from torch import nn

from app import main, model_loader, pipeline
from app.job_store import JobStore
from app.model_loader import load_model_checkpoint
from audio_sep.legacy_model import DemucsLite
from audio_sep.model import DemucsLiteV2

SOURCES = ("vocals", "drums", "bass", "other")


class NamedTestSeparator(nn.Module):
    sources = ("bass", "other", "drums", "vocals")
    samplerate = 44100
    audio_channels = 2
    segment = 0.01

    def forward(self, mixture):
        return torch.stack([mixture * factor for factor in (0.1, 0.2, 0.3, 0.4)], dim=1)


class ModelLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.old_threads)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_legacy_checkpoint_infers_dimensions_and_keeps_source_order(self):
        original = DemucsLite(channels=4, depth=2, lstm_layers=2).eval()
        path = self.root / "legacy.pth"
        order = ("bass", "drums", "other", "vocals")
        torch.save({"model_state_dict": original.state_dict(), "epoch": 17,
                    "source_names": list(order), "model_config": {"channels": 4, "depth": 2}}, path)
        loaded, metadata = load_model_checkpoint(path)
        self.assertEqual(loaded.sources, order)
        self.assertEqual(metadata["model_kind"], "legacy_lite")
        self.assertEqual(metadata["epoch"], 17)
        self.assertEqual(metadata["model_config"]["lstm_layers"], 2)
        mixture = torch.randn(1, 2, 513)
        with torch.inference_mode():
            torch.testing.assert_close(loaded(mixture), original(mixture))

    def test_raw_legacy_state_uses_original_canonical_order(self):
        path = self.root / "raw.pth"
        torch.save(DemucsLite(channels=4, depth=1).state_dict(), path)
        model, metadata = load_model_checkpoint(path)
        self.assertEqual(model.sources, SOURCES)
        self.assertEqual(metadata["model_config"]["channels"], 4)

    def test_v2_checkpoint_uses_selected_ema_weights_and_named_order(self):
        original = DemucsLiteV2(sources=tuple(reversed(SOURCES)), channels=4, depth=2,
                               max_channels=8, lstm_layers=0, dconv_depth=0).eval()
        selected = {key: value.clone() for key, value in original.state_dict().items()}
        unselected = {key: torch.zeros_like(value) for key, value in selected.items()}
        path = self.root / "v2.pth"
        torch.save({"format_version": 2, "model_kind": "lite", "model_config": original.export_config(),
                    "model_state_dict": unselected, "ema_state_dict": selected,
                    "selected_weights": "ema", "epoch": 9}, path)
        model, metadata = load_model_checkpoint(path)
        self.assertEqual(model.sources, tuple(reversed(SOURCES)))
        self.assertEqual(metadata["model_kind"], "lite")
        self.assertEqual(metadata["selected_weights"], "ema")
        mixture = torch.randn(1, 2, 513)
        with torch.inference_mode():
            torch.testing.assert_close(model(mixture), original(mixture))

    def test_missing_model_and_conflicting_dimensions_fail(self):
        with self.assertRaises(FileNotFoundError):
            load_model_checkpoint(self.root / "missing.pth")
        path = self.root / "wrong.pth"
        torch.save({"model_state_dict": DemucsLite(channels=4, depth=1).state_dict(),
                    "model_config": {"channels": 32}}, path)
        with self.assertRaisesRegex(ValueError, "disagree about channels"):
            load_model_checkpoint(path)


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_mono_native_audio_is_stereo_and_not_renormalized(self):
        path = self.root / "mono.wav"
        values = np.array([0.1, -0.3, 0.7], dtype=np.float32)
        sf.write(path, values, 44100, subtype="FLOAT")
        actual = pipeline.decode_audio(path)
        self.assertEqual(tuple(actual.shape), (2, 3))
        torch.testing.assert_close(actual[0], torch.from_numpy(values))
        torch.testing.assert_close(actual[0], actual[1])

    def test_ffmpeg_fallback_has_explicit_stereo_samplerate_and_no_shell(self):
        expected = np.array([[0.1, -0.2], [0.3, 0.4]], dtype="<f4")
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=expected.tobytes(), stderr=b"")
        with patch.object(pipeline.sf, "read", side_effect=RuntimeError("unsupported codec")), \
                patch.object(pipeline.subprocess, "run", return_value=result) as run:
            actual = pipeline.decode_audio(self.root / "sample.m4a")
        torch.testing.assert_close(actual, torch.from_numpy(expected.T.copy()))
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-ac") + 1], "2")
        self.assertEqual(command[command.index("-ar") + 1], "44100")
        self.assertNotIn("shell", run.call_args.kwargs)

    @unittest.skipUnless(shutil.which(pipeline.FFMPEG_BINARY), "FFmpeg unavailable")
    def test_real_ffmpeg_resamples_nonstandard_rate(self):
        path = self.root / "lowrate.wav"
        sf.write(path, np.linspace(-0.1, 0.1, 2205), 22050)
        audio = pipeline.decode_audio(path)
        self.assertEqual(tuple(audio.shape), (2, 4410))
        self.assertTrue(torch.isfinite(audio).all())

    def test_empty_nonfinite_and_incomplete_audio_rejected(self):
        for samples in (np.empty((0, 2), dtype=np.float32), np.array([[np.nan, 0]], dtype=np.float32)):
            with patch.object(pipeline.sf, "read", return_value=(samples, 44100)):
                with self.assertRaisesRegex(ValueError, "nonempty, finite"):
                    pipeline.decode_audio("invalid.wav")
        with patch.object(pipeline.sf, "read", side_effect=RuntimeError()), \
                patch.object(pipeline.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"short", b"")):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                pipeline.decode_audio("invalid.mp3")

    def test_pcm16_export_keeps_named_stem_ratios_with_one_common_gain(self):
        values = torch.stack([torch.full((2, 50), value) for value in (2.0, 0.5, -1.0, 0.0)])
        order = ("bass", "vocals", "drums", "other")
        gain = pipeline.export_pcm_stems(values, self.root, order)
        self.assertAlmostEqual(gain, (32767 / 32768) / 2)
        for index, source in enumerate(order):
            actual, sample_rate = sf.read(self.root / f"{source}.wav", dtype="float32", always_2d=True)
            self.assertEqual(sample_rate, 44100)
            self.assertEqual(sf.info(self.root / f"{source}.wav").subtype, "PCM_16")
            np.testing.assert_allclose(actual, values[index].numpy().T * gain, atol=1 / 32768)

    def test_export_does_not_boost_quiet_stems_and_rejects_nan(self):
        quiet = torch.full((4, 2, 10), 0.01)
        self.assertEqual(pipeline.export_pcm_stems(quiet, self.root, SOURCES), 1)
        quiet[0, 0, 0] = float("nan")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            pipeline.export_pcm_stems(quiet, self.root, SOURCES)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.uploads = self.root / "uploads"
        self.results = self.root / "results"
        self.uploads.mkdir()
        self.results.mkdir()
        self.store = JobStore()
        self.stack = ExitStack()
        static = next(route.app for route in main.app.routes if getattr(route, "path", None) == "/files")
        for target, attribute, value in (
            (main, "UPLOAD_DIR", self.uploads), (main, "PUBLIC_BASE_URL", ""),
            (pipeline, "RESULT_DIR", self.results),
            (main, "job_store", self.store), (pipeline, "job_store", self.store),
            (main, "load_model", lambda: None),
            (model_loader, "_model", NamedTestSeparator()), (model_loader, "_device", "cpu"),
            (model_loader, "_metadata", {"model_kind": "lite", "epoch": 3, "sources": list(NamedTestSeparator.sources)}),
            (static, "directory", str(self.results)), (static, "all_directories", [str(self.results)]),
        ):
            self.stack.enter_context(patch.object(target, attribute, value))
        self.client = self.stack.enter_context(TestClient(main.app, base_url="http://10.0.2.2:8000"))

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def wav_bytes(self):
        buffer = io.BytesIO()
        sf.write(buffer, np.full((513, 2), 0.25, dtype=np.float32), 44100, format="WAV", subtype="FLOAT")
        return buffer.getvalue()

    def test_upload_status_named_downloads_and_emulator_origin(self):
        response = self.client.post("/separate", files={"file": ("input.wav", self.wav_bytes(), "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        job_id = response.json()["job_id"]
        job = self.client.get(f"/status/{job_id}").json()
        self.assertEqual(job["status"], "done")
        self.assertEqual(set(job["result_urls"]), {f"{source}.wav" for source in SOURCES})
        for source, fraction in zip(NamedTestSeparator.sources, (0.1, 0.2, 0.3, 0.4)):
            url = job["result_urls"][f"{source}.wav"]
            self.assertTrue(url.startswith("http://10.0.2.2:8000/files/"))
            download = self.client.get(urlparse(url).path)
            self.assertEqual(download.status_code, 200)
            audio, rate = sf.read(io.BytesIO(download.content), dtype="float32", always_2d=True)
            self.assertEqual(rate, 44100)
            np.testing.assert_allclose(audio, 0.25 * fraction, atol=1 / 32768)
        self.assertEqual(list(self.uploads.iterdir()), [])
        health = self.client.get("/health").json()
        self.assertTrue(health["ready"])
        self.assertEqual(health["model_kind"], "lite")
        self.assertEqual(health["epoch"], 3)

    def test_invalid_empty_oversized_uploads_are_cleaned_up(self):
        for name, content, status in (("bad.txt", b"bad", 400), ("empty.wav", b"", 400)):
            response = self.client.post("/separate", files={"file": (name, content)})
            self.assertEqual(response.status_code, status)
            self.assertEqual(list(self.uploads.iterdir()), [])
        with patch.object(main, "MAX_UPLOAD_MB", 1):
            response = self.client.post("/separate", files={"file": ("large.wav", b"x" * (1024 * 1024 + 1))})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(self.client.get("/status/unknown").status_code, 404)

    def test_pipeline_failure_is_explicit_and_input_is_removed(self):
        with patch.object(pipeline, "decode_audio", side_effect=ValueError("corrupt audio")):
            response = self.client.post("/separate", files={"file": ("bad.wav", b"invalid audio")})
        job_id = response.json()["job_id"]
        job = self.client.get(f"/status/{job_id}").json()
        self.assertEqual(job["status"], "failed")
        self.assertIn("corrupt audio", job["error"])
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertFalse((self.results / job_id).exists())

    def test_inference_lock_serializes_jobs(self):
        active = 0
        maximum = 0
        guard = threading.Lock()

        def inference(model, mixture, **kwargs):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with guard:
                active -= 1
            return torch.zeros(4, 2, 10)

        inputs = []
        for index in range(2):
            path = self.uploads / f"{index}.wav"
            path.write_bytes(self.wav_bytes())
            self.store.create(str(index), path.name)
            inputs.append((str(index), str(path)))
        with patch.object(pipeline, "overlap_add", side_effect=inference):
            threads = [threading.Thread(target=pipeline.run_separation_pipeline, args=args) for args in inputs]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
        self.assertEqual(maximum, 1)
        for job_id, _ in inputs:
            self.assertEqual(self.store.get(job_id)["status"], "done")
        self.assertEqual(list(self.uploads.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
