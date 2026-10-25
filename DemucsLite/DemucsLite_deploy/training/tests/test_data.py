"""Synthetic tests for alignment, held-out songs, and augmentation physics."""

import json
from pathlib import Path
import tempfile
import unittest
import warnings

import numpy as np
import soundfile as sf
import torch

from audio_sep.data import DEFAULT_SOURCES, KNOWN_LEFT_MIX_ERRATUM, MUSDBDataset, load_manifest, scan_dataset


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def track(self, name="Synthetic Song", split="train", seed=7, subtype="FLOAT", frames=3000):
        path = self.root / split / name
        path.mkdir(parents=True)
        rng = np.random.default_rng(seed)
        targets = []
        for index, source in enumerate(DEFAULT_SOURCES):
            mono = rng.normal(0, 0.025 * (index + 1), frames).astype(np.float32)
            # Unequal channels detect accidental mono conversion.
            stem = np.stack([mono, mono * 0.37], axis=-1)
            sf.write(path / f"{source}.wav", stem, 44100, subtype=subtype)
            targets.append(stem)
        sf.write(path / "mixture.wav", np.stack(targets).sum(axis=0), 44100, subtype=subtype)
        return path

    def scan(self, **kwargs):
        return scan_dataset(self.root, strict=False, **kwargs)

    def test_official_song_split_has_no_crop_leakage_and_manifest_relocates(self):
        self.track()
        self.track(name="Actions - One Minute Smile", seed=8)
        self.track(name="Held-out Test Song", split="test", seed=9)
        output = self.root / "manifest.json"
        records = self.scan(output=output)
        splits = {record["track_name"]: record["subset"] for record in records}
        self.assertEqual(splits, {"Synthetic Song": "train", "Actions - One Minute Smile": "val", "Held-out Test Song": "test"})
        self.assertEqual(records, load_manifest(output))
        relocated_root = (self.root / "relocated").resolve()
        relocated = load_manifest(output, root=relocated_root)
        for record in relocated:
            self.assertEqual(Path(record["path"]).relative_to(relocated_root), Path(record["relative_path"]))
        audit = json.loads((self.root / "manifest.audit.json").read_text())
        self.assertEqual(audit["counts"], {"train": 1, "val": 1, "test": 1})
        self.assertFalse(audit["errors"])
        self.assertIn("active_fraction", audit["tracks"][0]["probes"][0])
        with self.assertRaisesRegex(ValueError, "Expected 100"):
            scan_dataset(self.root)

    def test_alignment_sample_rate_and_stereo_are_checked(self):
        path = self.track()
        sf.write(path / "bass.wav", np.zeros((2999, 2)), 44100, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "bass.wav: 2999 frames"):
            self.scan()
        sf.write(path / "bass.wav", np.zeros((3000, 1)), 22050, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "expected 44100 Hz stereo"):
            self.scan()

    def test_quantization_rounding_is_tolerated_but_bad_mixture_fails(self):
        path = self.track(subtype="PCM_16")
        with warnings.catch_warnings(record=True) as caught:
            self.scan()
        self.assertEqual(len(caught), 0)
        sf.write(path / "mixture.wav", np.full((3000, 2), 0.25), 44100, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "mixture/stem residual"):
            self.scan()

    def test_nonfinite_probe_and_train_test_duplicates_fail(self):
        path = self.track()
        bad = np.zeros((3000, 2), np.float32)
        bad[0, 0] = np.nan
        sf.write(path / "vocals.wav", bad, 44100, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.scan()
        sf.write(path / "vocals.wav", np.zeros((3000, 2)), 44100, subtype="FLOAT")
        self.track(split="test")
        with self.assertRaisesRegex(ValueError, "Training/test track-name overlap"):
            self.scan()

    def test_known_test_left_erratum_is_audited_and_original_audio_is_preserved(self):
        path = self.track(name="PR - Oh No", split="test")
        mixture, sr = sf.read(path / "mixture.wav", dtype="float32", always_2d=True)
        mixture[:, 0] += np.float32(0.25)
        sf.write(path / "mixture.wav", mixture, sr, subtype="FLOAT")
        originals = {name: (path / f"{name}.wav").read_bytes() for name in ("mixture", *DEFAULT_SOURCES)}
        output = self.root / "manifest.json"
        with warnings.catch_warnings(record=True) as caught:
            records = self.scan(output=output)
        self.assertTrue(any("known MUSDB erratum on left channel" in str(item.message) for item in caught))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["subset"], "test")
        self.assertEqual(records[0]["known_issue"], KNOWN_LEFT_MIX_ERRATUM)
        self.assertEqual(records[0]["residual_policy"], "warn_known_artistic_mix")
        self.assertGreater(records[0]["max_probe_residual_rms_by_channel"]["left"], 0.2)
        self.assertLess(records[0]["max_probe_residual_rms_by_channel"]["right"], 1e-6)
        self.assertEqual(records, load_manifest(output))
        audit = json.loads((self.root / "manifest.audit.json").read_text())
        self.assertFalse(audit["errors"])
        self.assertEqual(audit["tracks"][0]["known_issue"], KNOWN_LEFT_MIX_ERRATUM)
        self.assertTrue(audit["known_errata_policy"]["original_mixture_stems_preserved"])
        channels = audit["tracks"][0]["probes"][0]["residual_by_channel"]
        self.assertGreater(channels["left"]["residual_rms"], channels["left"]["failure_floor"])
        self.assertLess(channels["right"]["residual_rms"], channels["right"]["failure_floor"])
        dataset = MUSDBDataset(records, training=False, segment_seconds=0.02, validation_crops=1)
        actual_mix, actual_stems = dataset[0]
        offset = (3000 - 882) // 2
        torch.testing.assert_close(actual_mix, torch.from_numpy(mixture[offset:offset + 882].T.copy()), rtol=0, atol=0)
        expected_stems = torch.stack([
            torch.from_numpy(sf.read(path / f"{name}.wav", start=offset, frames=882,
                                     dtype="float32", always_2d=True)[0].T.copy())
            for name in DEFAULT_SOURCES
        ])
        torch.testing.assert_close(actual_stems, expected_stems, rtol=0, atol=0)
        self.assertFalse(torch.allclose(actual_mix, actual_stems.sum(0)))
        self.assertEqual(originals, {name: (path / f"{name}.wav").read_bytes() for name in originals})
        with self.assertRaisesRegex(ValueError, "left channel mixture/stem residual"):
            self.scan(allow_known_errata=False)

    def test_known_track_observed_right_residual_warns_and_strict_mode_rejects_both(self):
        path = self.track(name="PR - Oh No", split="test", subtype="PCM_16", frames=88200)
        mixture, sr = sf.read(path / "mixture.wav", dtype="float32", always_2d=True)
        mixture[:, 0] += np.float32(0.25)
        # Reproduce the newly observed right RMS levels at two spread probes.
        mixture[:44100, 1] += np.float32(0.031924)
        mixture[44100:, 1] += np.float32(0.021888)
        sf.write(path / "mixture.wav", mixture, sr, subtype="PCM_16")
        originals = {name: (path / f"{name}.wav").read_bytes() for name in ("mixture", *DEFAULT_SOURCES)}
        output = self.root / "manifest.json"
        with warnings.catch_warnings(record=True) as caught:
            records = self.scan(output=output, probe_seconds=0.25)
        messages = [str(item.message) for item in caught]
        self.assertTrue(any("known MUSDB erratum on left channel" in message for message in messages))
        self.assertTrue(any("additional observed right-channel residual" in message for message in messages))
        self.assertTrue(any("official erratum describes the left channel" in message for message in messages))
        self.assertEqual(records[0]["residual_policy"], "warn_known_artistic_mix")
        self.assertEqual(len(records), 1)
        self.assertTrue(output.exists())
        audit = json.loads((self.root / "manifest.audit.json").read_text())
        self.assertFalse(audit["errors"])
        probes = audit["tracks"][0]["probes"]
        self.assertAlmostEqual(probes[0]["residual_by_channel"]["right"]["residual_rms"], 0.031924, delta=5e-5)
        self.assertAlmostEqual(probes[-1]["residual_by_channel"]["right"]["residual_rms"], 0.021888, delta=5e-5)
        for probe in probes:
            diagnostic = probe["residual_by_channel"]["right"]
            self.assertGreater(diagnostic["residual_rms"], diagnostic["failure_floor"])
            self.assertGreaterEqual(diagnostic["failure_floor"], 20 * 2**-15)
        self.assertEqual(audit["known_errata_policy"]["official_erratum_channels"], ["left"])
        self.assertEqual(audit["known_errata_policy"]["additional_observed_residual_channels"], ["right"])
        self.assertEqual(originals, {name: (path / f"{name}.wav").read_bytes() for name in originals})
        with self.assertRaises(ValueError) as error:
            self.scan(allow_known_errata=False, probe_seconds=0.25)
        self.assertIn("left channel mixture/stem residual", str(error.exception))
        self.assertIn("right channel mixture/stem residual", str(error.exception))

    def test_erratum_is_scoped_to_exact_track_name_and_physical_test_split(self):
        for split, name in (("train", "PR - Oh No"), ("test", "Unknown Residual Song")):
            with self.subTest(split=split, name=name):
                path = self.track(name=name, split=split)
                mixture, sr = sf.read(path / "mixture.wav", dtype="float32", always_2d=True)
                mixture[:, 0] += np.float32(0.25)
                sf.write(path / "mixture.wav", mixture, sr, subtype="FLOAT")
                with self.assertRaisesRegex(ValueError, f"{split}/{name}: mixture/stem residual"):
                    self.scan()

    def test_known_erratum_still_rejects_nonfinite_samples_and_length_mismatch(self):
        path = self.track(name="PR - Oh No", split="test")
        bass, sr = sf.read(path / "bass.wav", dtype="float32", always_2d=True)
        bass[0, 0] = np.nan
        sf.write(path / "bass.wav", bass, sr, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.scan()
        sf.write(path / "bass.wav", np.zeros((2999, 2)), sr, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "bass.wav: 2999 frames"):
            self.scan()

    def test_training_remix_preserves_stereo_and_exact_sum_with_shared_scale(self):
        self.track(seed=1)
        self.track(name="Second Train Song", seed=2)
        records = self.scan()
        dataset = MUSDBDataset(records, segment_seconds=0.02, crops_per_track=4, remix_prob=1.0, gain_db=15)
        mixture, targets = dataset[0]
        self.assertEqual(tuple(mixture.shape), (2, 882))
        self.assertEqual(tuple(targets.shape), (4, 2, 882))
        self.assertTrue(torch.equal(mixture, targets.sum(dim=0)))
        self.assertLessEqual(float(mixture.abs().max()), 1.0)
        self.assertLessEqual(float(targets.abs().max()), 1.0)
        for source in targets:
            self.assertFalse(torch.equal(source[0], source[1]))
            ratio = float(source[1].norm() / source[0].norm())
            self.assertTrue(abs(ratio - 0.37) < 1e-5 or abs(ratio - 1 / 0.37) < 1e-5)
        self.assertTrue(torch.equal(mixture, dataset[0][0]))
        dataset.set_epoch(1)
        self.assertFalse(torch.equal(mixture, dataset[0][0]))
        bad_records = [dict(records[0], subset="val")]
        with self.assertRaisesRegex(ValueError, "Training dataset includes val"):
            MUSDBDataset(bad_records)

    def test_validation_is_deterministic_uses_original_mixture_and_no_augmentation(self):
        path = self.track(name="Actions - One Minute Smile")
        # A small export residual lets this test distinguish the original
        # mixture from the sum reconstructed for augmented training samples.
        mixture, sr = sf.read(path / "mixture.wav", dtype="float32", always_2d=True)
        mixture += np.float32(1e-6)
        sf.write(path / "mixture.wav", mixture, sr, subtype="FLOAT")
        records = self.scan()
        dataset = MUSDBDataset(records, segment_seconds=0.02, training=False, validation_crops=3)
        expected_offsets = (0, (3000 - 882) // 2, 3000 - 882)
        for index, offset in enumerate(expected_offsets):
            actual, _ = dataset[index]
            expected = torch.from_numpy(mixture[offset:offset + 882].T.copy())
            self.assertTrue(torch.equal(actual, expected))
            dataset.set_epoch(200)
            self.assertTrue(torch.equal(actual, dataset[index][0]))
        alternate_seed = MUSDBDataset(records, segment_seconds=0.02, training=False, validation_crops=3, seed=987)
        self.assertTrue(torch.equal(dataset[1][0], alternate_seed[1][0]))

    def test_stale_manifest_is_rejected_and_short_tracks_are_padded_together(self):
        path = self.track(frames=200)
        records = self.scan()
        dataset = MUSDBDataset(records, segment_seconds=0.02, training=False)
        mixture, targets = dataset[0]
        self.assertTrue(torch.equal(mixture[:, 200:], torch.zeros(2, 682)))
        self.assertTrue(torch.equal(targets[..., 200:], torch.zeros(4, 2, 682)))
        sf.write(path / "drums.wav", np.zeros((201, 2)), 44100, subtype="FLOAT")
        with self.assertRaisesRegex(ValueError, "WAV/manifest mismatch"):
            MUSDBDataset(records)


if __name__ == "__main__":
    unittest.main()
