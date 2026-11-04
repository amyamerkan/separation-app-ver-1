import unittest

import torch

from audio_sep.losses import multi_resolution_stft_loss, separation_loss
from audio_sep.metrics import metrics_per_source
from audio_sep.model import DemucsLiteV2, count_parameters


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tiny CPU kernels suffer badly from oversized machine thread pools.
        torch.set_num_threads(1)

    def tiny(self, **overrides):
        config = dict(channels=4, depth=2, kernel_size=4, stride=2, lstm_layers=1, dconv_depth=1)
        config.update(overrides)
        return DemucsLiteV2(**config)

    def test_shapes_for_odd_short_and_valid_lengths(self):
        model = self.tiny()
        for length in (1, 5, 31, 129):
            with self.subTest(length=length):
                output = model(torch.randn(1, 2, length))
                self.assertEqual(tuple(output.shape), (1, 4, 2, length))
                self.assertTrue(torch.isfinite(output).all())
                self.assertGreaterEqual(model.valid_length(length), length)
        self.assertGreater(count_parameters(model), 0)

    def test_deep_context_and_disabled_lstm_receive_gradient(self):
        model = self.tiny(depth=3, lstm_layers=0)
        output = model(torch.randn(1, 2, 67))
        output.square().mean().backward()
        self.assertTrue(all(p.grad is not None for p in model.parameters()))
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters()))

    def test_export_config_preserves_order_and_exact_predictions(self):
        model = self.tiny(sources=("other", "vocals", "drums", "bass")).eval()
        clone = DemucsLiteV2(**model.export_config()).eval()
        clone.load_state_dict(model.state_dict())
        waveform = torch.randn(2, 2, 73)
        self.assertEqual(clone.sources, model.sources)
        torch.testing.assert_close(clone(waveform), model(waveform))

    def test_normalization_restores_mean_once(self):
        model = self.tiny(lstm_layers=0)
        for parameter in model.parameters():
            parameter.data.zero_()
        mixture = torch.full((1, 2, 71), 0.4)
        estimates = model(mixture)
        torch.testing.assert_close(estimates, torch.full_like(estimates, 0.1))
        torch.testing.assert_close(estimates.sum(dim=1), mixture)

    def test_optional_consistency_preserves_each_stereo_channel(self):
        model = self.tiny(mixture_consistency=True)
        mixture = torch.randn(2, 2, 101) * 0.2 + 0.07
        estimate = model(mixture)
        torch.testing.assert_close(estimate.sum(dim=1), mixture, atol=1e-6, rtol=1e-5)


class LossAndMetricTests(unittest.TestCase):
    def test_antiphase_stereo_is_not_discarded_by_spectral_loss(self):
        left = torch.sin(torch.arange(257).float() * 0.19)
        target = torch.stack((left, -left))[None, None]
        estimate = torch.zeros_like(target, requires_grad=True)
        loss = multi_resolution_stft_loss(estimate, target, fft_sizes=(32, 64))
        self.assertGreater(float(loss), 0.5)
        loss.backward()
        self.assertTrue(torch.isfinite(estimate.grad).all())

    def test_silent_targets_have_finite_nonzero_gradient(self):
        estimate = torch.full((1, 4, 2, 23), 0.01, requires_grad=True)
        target = torch.zeros_like(estimate)
        mixture = target.sum(dim=1)
        loss, parts = separation_loss(estimate, target, mixture, fft_sizes=(32, 64))
        self.assertTrue(torch.isfinite(loss))
        self.assertGreater(float(parts["silence"]), 0)
        loss.backward()
        self.assertTrue(torch.isfinite(estimate.grad).all())
        self.assertGreater(float(estimate.grad.abs().sum()), 0)
        metrics = metrics_per_source(estimate.detach(), target)
        self.assertFalse(metrics["active"].any())
        self.assertTrue(torch.isfinite(metrics["si_sdr_db"]).all())
        self.assertGreater(float(metrics["silent_estimate_energy"].mean()), 0)

    def test_exact_silence_has_no_nan_gradients(self):
        estimate = torch.zeros((1, 4, 2, 17), requires_grad=True)
        loss, _ = separation_loss(estimate, torch.zeros_like(estimate), estimate.detach().sum(dim=1), fft_sizes=(32,))
        loss.backward()
        self.assertTrue(torch.isfinite(estimate.grad).all())
        self.assertAlmostEqual(float(loss), 0.0, places=6)

    def test_equal_relative_error_has_equal_weight_for_quiet_stem(self):
        target = torch.ones((1, 2, 2, 17))
        target[:, 1] *= 0.2
        loss, parts = separation_loss(0.9 * target, target, target.sum(dim=1),
                                      spectral_weight=0, si_sdr_weight=0, consistency_weight=0)
        self.assertAlmostEqual(float(parts["source_l1"]), 0.1, places=5)
        self.assertAlmostEqual(float(loss), 0.1, places=5)

    def test_metrics_distinguish_gain_error_from_scale_invariant_score(self):
        torch.manual_seed(10)
        target = torch.randn(2, 4, 2, 257) * 0.1
        metrics = metrics_per_source(0.5 * target, target)
        self.assertTrue(metrics["active"].all())
        self.assertLess(float((metrics["snr_db"] - 6.0206).abs().max()), 0.02)
        self.assertGreater(float(metrics["si_sdr_db"].mean()), 40)

    def test_stereo_swap_is_detected(self):
        torch.manual_seed(5)
        target = torch.randn(1, 1, 2, 257) * 0.1
        good = metrics_per_source(target, target)
        swapped = metrics_per_source(target.flip(dims=(2,)), target)
        self.assertGreater(float(good["snr_db"]), float(swapped["snr_db"]) + 30)
        self.assertGreater(float(good["si_sdr_db"]), float(swapped["si_sdr_db"]) + 30)


if __name__ == "__main__":
    unittest.main()
