import json
import io
import copy
from contextlib import redirect_stderr, redirect_stdout
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
import torch

from audio_sep.data import DEFAULT_SOURCES, scan_dataset
from audio_sep.inference import load_checkpoint


class GradientStepTest(unittest.TestCase):
    """CPU GradScaler exercises real overflow recovery without claiming CUDA QA."""

    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_amp_overflow_skips_weights_ema_and_step_then_recovers(self):
        from audio_sep.train import checked_optimizer_step
        model = torch.nn.Linear(2, 1, bias=False)
        with torch.no_grad():
            model.weight.fill_(0.2)
        ema = copy.deepcopy(model).requires_grad_(False)
        with torch.no_grad():
            ema.weight.fill_(0.8)
        optimizer = torch.optim.SGD(model.parameters(), lr=0.1, momentum=0.9)
        scaler = torch.amp.GradScaler("cpu", init_scale=16.0)
        weights_before, ema_before = model.weight.detach().clone(), ema.weight.detach().clone()
        scaler.scale(model(torch.ones(1, 2)).square().mean()).backward()
        model.weight.grad[0, 0] = float("inf")
        overflow = checked_optimizer_step(model, optimizer, scaler, step=7, ema=ema)
        self.assertFalse(overflow["stepped"])
        self.assertFalse(overflow["gradient_entries_finite"])
        self.assertEqual(overflow["step"], 7)
        self.assertEqual(overflow["scale_before"], 16.0)
        self.assertEqual(overflow["scale_after"], 8.0)
        self.assertIsNone(model.weight.grad)
        self.assertFalse(optimizer.state)
        torch.testing.assert_close(model.weight, weights_before)
        torch.testing.assert_close(ema.weight, ema_before)
        scaler.scale(model(torch.ones(1, 2)).square().mean()).backward()
        healthy = checked_optimizer_step(model, optimizer, scaler, step=overflow["step"], ema=ema)
        self.assertTrue(healthy["stepped"])
        self.assertEqual(healthy["step"], 8)
        self.assertTrue(torch.isfinite(model.weight).all())
        self.assertFalse(torch.equal(model.weight, weights_before))
        self.assertFalse(torch.equal(ema.weight, ema_before))
        # Step=8 uses decay=9/18. A skipped step must not change that schedule.
        torch.testing.assert_close(ema.weight, 0.5 * ema_before + 0.5 * model.weight)

    def test_finite_large_gradients_clip_with_float64_norm(self):
        from audio_sep.train import checked_optimizer_step
        model = torch.nn.Linear(2, 1, bias=False)
        with torch.no_grad():
            model.weight.zero_()
        model.weight.grad = torch.full_like(model.weight, 1e20)
        # The old float32 norm overflows although all gradient entries are finite.
        self.assertTrue(torch.isfinite(model.weight.grad).all())
        self.assertFalse(torch.isfinite(torch.linalg.vector_norm(model.weight.grad)))
        optimizer = torch.optim.SGD(model.parameters(), lr=1.0)
        scaler = torch.amp.GradScaler("cpu", enabled=False)
        result = checked_optimizer_step(model, optimizer, scaler, max_norm=5.0)
        self.assertTrue(result["stepped"])
        self.assertTrue(result["gradient_entries_finite"])
        self.assertAlmostEqual(result["grad_norm"] / 1e20, 2**0.5, places=5)
        self.assertTrue(torch.isfinite(model.weight).all())
        self.assertAlmostEqual(float(torch.linalg.vector_norm(model.weight.detach())), 5.0, places=5)

    def test_fp32_nonfinite_gradients_remain_fatal(self):
        from audio_sep.train import checked_optimizer_step
        for bad_value in (float("inf"), float("nan")):
            with self.subTest(bad_value=bad_value):
                model = torch.nn.Linear(2, 1, bias=False)
                before = model.weight.detach().clone()
                model.weight.grad = torch.full_like(model.weight, bad_value)
                optimizer = torch.optim.SGD(model.parameters(), lr=1.0)
                scaler = torch.amp.GradScaler("cpu", enabled=False)
                with self.assertRaisesRegex(FloatingPointError, "Nonfinite FP32 gradient entries"):
                    checked_optimizer_step(model, optimizer, scaler)
                torch.testing.assert_close(model.weight, before)
                self.assertIsNone(model.weight.grad)

    def test_scaler_restore_allows_explicit_precision_mode_changes(self):
        from audio_sep.train import restore_scaler_state
        amp = torch.amp.GradScaler("cpu", init_scale=16.0)
        state = amp.state_dict()
        fp32 = torch.amp.GradScaler("cpu", enabled=False)
        self.assertEqual(restore_scaler_state(fp32, state), "disabled")
        self.assertEqual(fp32.state_dict(), {})
        fresh_amp = torch.amp.GradScaler("cpu", init_scale=32.0)
        self.assertEqual(restore_scaler_state(fresh_amp, fp32.state_dict()), "fresh")
        self.assertEqual(fresh_amp.get_scale(), 32.0)
        self.assertEqual(restore_scaler_state(fresh_amp, state), "restored")
        self.assertEqual(fresh_amp.get_scale(), 16.0)

    def test_persistent_amp_overflow_stops_after_bounded_consecutive_groups(self):
        from audio_sep import train
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = TrainingTest().synthetic_manifest(root)
            run = root / "run"
            command = ["audio_sep.train", "--manifest", str(manifest), "--run-dir", str(run),
                       "--channels", "4", "--depth", "2", "--segment", "0.02",
                       "--train-crops", "12", "--val-crops", "2", "--workers", "0",
                       "--device", "cpu", "--epochs", "1", "--accumulate", "1"]
            scales, steps = [], []

            def persistent_overflow(model, optimizer, scaler, *, step, **kwargs):
                scales.append(16.0 / 2**len(scales))
                steps.append(step)
                optimizer.zero_grad(set_to_none=True)
                return {"stepped": False, "step": step, "scale_before": scales[-1],
                        "scale_after": scales[-1] / 2}

            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                with patch.object(sys, "argv", command), patch.object(train, "checked_optimizer_step", persistent_overflow):
                    with self.assertRaisesRegex(FloatingPointError, "8 consecutive nonfinite-gradient groups"):
                        train.main()
            self.assertEqual(len(scales), train.MAX_CONSECUTIVE_AMP_OVERFLOWS)
            self.assertEqual(steps, [0] * train.MAX_CONSECUTIVE_AMP_OVERFLOWS)
            self.assertIn("scale 16 -> 8", stdout.getvalue())
            self.assertFalse((run / "last.pth").exists())
            self.assertFalse((run / "best.pth").exists())


class TrainingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def synthetic_manifest(self, root):
        sample = np.arange(4410) / 44100
        for subset, name in (("train", "Synthetic Train"),
                             ("train", "Actions - One Minute Smile"),
                             ("test", "Synthetic Test")):
            directory = root / "dataset" / subset / name
            directory.mkdir(parents=True)
            stems = []
            for i, source in enumerate(DEFAULT_SOURCES):
                x = (0.02 * np.sin(2 * np.pi * (110 + 80 * i) * sample)).astype("float32")
                stereo = np.stack((x, 0.7 * x), axis=1)
                sf.write(directory / f"{source}.wav", stereo, 44100, subtype="FLOAT")
                stems.append(stereo)
            sf.write(directory / "mixture.wav", np.sum(stems, axis=0), 44100, subtype="FLOAT")
        manifest = root / "manifest.json"
        scan_dataset(root / "dataset", manifest, strict=False)
        return manifest

    def test_latest_best_export_survives_interruption_in_later_epoch(self):
        from audio_sep import train
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.synthetic_manifest(root)
            run = root / "run"
            command = ["audio_sep.train", "--manifest", str(manifest), "--run-dir", str(run),
                       "--channels", "4", "--depth", "2", "--segment", "0.02",
                       "--train-crops", "2", "--val-crops", "2", "--workers", "0",
                       "--device", "cpu", "--epochs", "2"]
            real_validate = train.validate
            calls = 0

            def interrupt_second_epoch(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3:  # epoch 1 raw + EMA completed; epoch 2 is interrupted.
                    raise RuntimeError("Simulated runtime interruption")
                return real_validate(*args, **kwargs)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with patch.object(sys, "argv", command), patch.object(train, "validate", side_effect=interrupt_second_epoch):
                    with self.assertRaisesRegex(RuntimeError, "Simulated runtime interruption"):
                        train.main()
            last = torch.load(run / "last.pth", weights_only=False)
            best = torch.load(run / "best.pth", weights_only=False)
            model, export = load_checkpoint(run / "best_model.pth")
            self.assertEqual(last["epoch"], 1)
            self.assertEqual(export["epoch"], best["epoch"])
            self.assertEqual(export["best_snr_db"], best["best_snr_db"])
            selected = best["ema_state_dict"] if best["selected_weights"] == "ema" else best["model_state_dict"]
            for key, value in model.state_dict().items():
                torch.testing.assert_close(value, selected[key])
            self.assertNotIn("optimizer_state_dict", export)
            self.assertTrue(torch.isfinite(model(torch.randn(1, 2, 882))).all())

    def test_pretrained_baseline_export_survives_before_first_training_crop(self):
        from audio_sep import train
        from audio_sep.data import MUSDBDataset
        from audio_sep.pretrained import PretrainedSeparator
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.synthetic_manifest(root)
            run = root / "run"
            model = PretrainedSeparator(
                init_args=[["drums", "bass", "other", "vocals"]],
                init_kwargs={"channels": 8, "t_layers": 1, "t_heads": 2, "dconv_depth": 0,
                             "segment": 0.2, "samplerate": 44100},
            )
            command = ["audio_sep.train", "--manifest", str(manifest), "--run-dir", str(run),
                       "--kind", "pretrained", "--segment", "0.02", "--train-crops", "2",
                       "--val-crops", "2", "--workers", "0", "--device", "cpu", "--epochs", "1"]
            real_getitem = MUSDBDataset.__getitem__

            def interrupt_training_crop(dataset, index):
                if dataset.training:
                    raise RuntimeError("Simulated interruption before training")
                return real_getitem(dataset, index)

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with patch.object(sys, "argv", command), patch.object(train, "build_model", return_value=model):
                    with patch.object(MUSDBDataset, "__getitem__", interrupt_training_crop):
                        with self.assertRaisesRegex(RuntimeError, "Simulated interruption before training"):
                            train.main()
            loaded, export = load_checkpoint(run / "best_model.pth")
            self.assertEqual(export["epoch"], 0)
            self.assertEqual(export["selected_weights"], "raw")
            self.assertTrue((run / "best.pth").exists())
            self.assertFalse((run / "last.pth").exists())
            for key, value in loaded.state_dict().items():
                torch.testing.assert_close(value, model.state_dict()[key])

    def test_train_resume_export_and_full_track_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = np.arange(4410) / 44100
            for subset, name in (("train", "Synthetic Train"),
                                 ("train", "Actions - One Minute Smile"),
                                 ("test", "Synthetic Test")):
                directory = root / "dataset" / subset / name
                directory.mkdir(parents=True)
                stems = []
                for i, source in enumerate(DEFAULT_SOURCES):
                    x = (0.02 * np.sin(2 * np.pi * (110 + 80 * i) * sample)).astype("float32")
                    stereo = np.stack((x, 0.7 * x), axis=1)
                    sf.write(directory / f"{source}.wav", stereo, 44100, subtype="FLOAT")
                    stems.append(stereo)
                sf.write(directory / "mixture.wav", np.sum(stems, axis=0), 44100, subtype="FLOAT")
            manifest = root / "manifest.json"
            scan_dataset(root / "dataset", manifest, strict=False)
            run = root / "run"
            from audio_sep.train import main as train_main
            from audio_sep.evaluate import main as evaluate_main
            # Invoke the CLI parser in-process: avoids platform OpenMP shared-memory
            # limits in subprocess imports and also keeps this CPU smoke test fast.
            base = ["audio_sep.train", "--manifest", str(manifest),
                    "--run-dir", str(run), "--channels", "4", "--depth", "2",
                    "--segment", "0.02", "--train-crops", "3", "--val-crops", "2",
                    "--batch-size", "1", "--accumulate", "2", "--workers", "0", "--device", "cpu"]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with patch.object(sys, "argv", [*base, "--epochs", "1"]):
                    train_main()
                # An enabled scaler state has the same schema on CPU/CUDA. This
                # simulates an existing AMP checkpoint for explicit FP32 resume.
                prior = torch.load(run / "last.pth", weights_only=False)
                prior["scaler_state_dict"] = torch.amp.GradScaler("cpu", init_scale=16.0).state_dict()
                prior["training_config"]["amp_enabled"] = True
                prior["training_config"]["precision_mode"] = "cuda_amp"
                torch.save(prior, run / "last.pth")
                with patch.object(sys, "argv", [*base, "--epochs", "2", "--resume", "--no-amp"]):
                    train_main()
            checkpoint = torch.load(run / "last.pth", weights_only=False)
            self.assertEqual(checkpoint["epoch"], 2)
            self.assertEqual(len(checkpoint["history"]), 2)
            self.assertEqual(checkpoint["scaler_state_dict"], {})
            self.assertEqual(checkpoint["training_config"]["precision_mode"], "fp32")
            self.assertEqual(checkpoint["training_config"]["resume_precision_from"], "cuda_amp")
            self.assertTrue(checkpoint["training_config"]["no_amp"])
            self.assertEqual(checkpoint["history"][-1]["amp_skipped_groups"], 0)
            model, exported = load_checkpoint(run / "best_model.pth")
            self.assertEqual(exported["sources"], list(DEFAULT_SOURCES))
            self.assertNotIn("optimizer_state_dict", exported)
            self.assertTrue(torch.isfinite(model(torch.randn(1, 2, 882))).all())
            report = root / "report.json"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with patch.object(sys, "argv", ["audio_sep.evaluate", "--manifest", str(manifest),
                                               "--checkpoint", str(run / "best_model.pth"),
                                               "--output", str(report), "--device", "cpu"]):
                    evaluate_main()
            self.assertEqual(len(json.loads(report.read_text())["tracks"]), 1)

    def test_htdemucs_forward_and_offline_checkpoint(self):
        from audio_sep.pretrained import PretrainedSeparator
        args = [["drums", "bass", "other", "vocals"]]
        kwargs = {"channels": 8, "t_layers": 1, "t_heads": 2, "dconv_depth": 0,
                  "segment": 0.2, "samplerate": 44100}
        model = PretrainedSeparator(init_args=args, init_kwargs=kwargs)
        mix = torch.randn(1, 2, 4410) * 0.1
        model.train()
        y = model(mix)
        self.assertEqual(tuple(y.shape), (1, 4, 2, 4410))
        y.square().mean().backward()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))
        self.assertAlmostEqual(float(model.backbone.segment), 0.2)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "model.pth"
            torch.save({"format_version": 2, "model_kind": "pretrained",
                        "model_config": model.export_config(), "model_state_dict": model.state_dict()}, path)
            loaded, _ = load_checkpoint(path)
            torch.testing.assert_close(loaded(mix), model.eval()(mix))


if __name__ == "__main__":
    unittest.main()
