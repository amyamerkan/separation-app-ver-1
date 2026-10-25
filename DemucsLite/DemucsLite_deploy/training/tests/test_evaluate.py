import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf
import torch

from audio_sep.data import DEFAULT_SOURCES
from audio_sep.evaluate import evaluation_report


class EvaluationTest(unittest.TestCase):
    def score_row(self, name, score, *, flagged=False):
        row = {"track_name": name, "snr_db": [score] * 4, "si_sdr_db": [score + 1] * 4}
        if flagged:
            row.update(known_issue="musdb18hq_pr_oh_no_left_mixture",
                       residual_policy="warn_known_artistic_mix")
        return row

    def test_primary_includes_flagged_track_and_secondary_excludes_only_flags(self):
        rows = [self.score_row("PR - Oh No", 2, flagged=True), self.score_row("Ordinary", 10)]
        report = evaluation_report(rows, {"subset": "test"})
        self.assertEqual(report["mixture_policy"], "original_mixture_wav")
        self.assertEqual(report["summary"]["macro_snr_db"], 6)
        self.assertEqual(report["summary"]["macro_si_sdr_db"], 7)
        self.assertEqual(report["summary_without_flagged_tracks"]["macro_snr_db"], 10)
        self.assertEqual(report["track_counts"], {"all": 2, "without_flagged": 1, "flagged": 1})
        self.assertEqual(report["flagged_tracks"], [{"track_name": "PR - Oh No",
                         "known_issue": "musdb18hq_pr_oh_no_left_mixture",
                         "residual_policy": "warn_known_artistic_mix"}])
        self.assertEqual(report["tracks"], rows)

    def test_all_flagged_tracks_have_no_secondary_score(self):
        rows = [self.score_row("PR - Oh No", 2, flagged=True)]
        report = evaluation_report(rows, {})
        self.assertEqual(report["summary"]["macro_snr_db"], 2)
        self.assertIsNone(report["summary_without_flagged_tracks"])
        self.assertEqual(report["track_counts"], {"all": 1, "without_flagged": 0, "flagged": 1})

    def test_cli_preserves_original_mixture_and_audit_provenance(self):
        from audio_sep import evaluate

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records, original_mixtures, targets = [], [], []
            time = np.arange(882, dtype=np.float32) / 44100
            for index, name in enumerate(("PR - Oh No", "Ordinary")):
                directory = root / name
                directory.mkdir()
                stems = []
                for source_index, source in enumerate(DEFAULT_SOURCES):
                    waveform = 0.03 * np.sin(2 * np.pi * (100 + 70 * source_index) * time)
                    stem = np.stack((waveform, 0.8 * waveform), axis=1).astype(np.float32)
                    sf.write(directory / f"{source}.wav", stem, 44100, subtype="FLOAT")
                    stems.append(stem)
                mixture = np.sum(stems, axis=0)
                if index == 0:
                    # Both-channel residual mirrors the policy decision, without
                    # representing this synthetic audio as the real dataset.
                    mixture = mixture + np.array([0.06, 0.03], dtype=np.float32)
                sf.write(directory / "mixture.wav", mixture, 44100, subtype="FLOAT")
                record = {"track_name": name, "subset": "test", "path": str(directory)}
                if index == 0:
                    record.update(known_issue="musdb18hq_pr_oh_no_left_mixture",
                                  residual_policy="warn_known_artistic_mix",
                                  max_probe_residual_rms_by_channel={"left": 0.06, "right": 0.03})
                records.append(record)
                original_mixtures.append(torch.from_numpy(mixture.T.copy()))
                targets.append(torch.from_numpy(np.stack(stems).transpose(0, 2, 1).copy()))

            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(records))
            output = root / "report.json"
            seen_mixtures = []

            def separate(model, mixture, **kwargs):
                seen_mixtures.append(mixture.clone())
                return targets[len(seen_mixtures) - 1] * 0.5

            model = SimpleNamespace(sources=DEFAULT_SOURCES)
            command = ["audio_sep.evaluate", "--manifest", str(manifest), "--checkpoint", "unused.pth",
                       "--output", str(output), "--device", "cpu"]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with patch.object(sys, "argv", command), patch.object(evaluate, "load_checkpoint", return_value=(model, {})):
                    with patch.object(evaluate, "overlap_add", side_effect=separate):
                        evaluate.main()

            self.assertEqual(len(seen_mixtures), 2)
            for actual, expected in zip(seen_mixtures, original_mixtures):
                torch.testing.assert_close(actual, expected)
            self.assertFalse(torch.allclose(seen_mixtures[0], targets[0].sum(0)))
            report = json.loads(output.read_text())
            self.assertEqual(report["mixture_policy"], "original_mixture_wav")
            self.assertEqual(report["track_counts"], {"all": 2, "without_flagged": 1, "flagged": 1})
            for key in ("known_issue", "residual_policy", "max_probe_residual_rms_by_channel"):
                self.assertEqual(report["tracks"][0][key], records[0][key])
            self.assertNotIn("known_issue", report["tracks"][1])


if __name__ == "__main__":
    unittest.main()
