import unittest

import numpy as np

from src.quantization import embed_bit, extract_bit


class EnergyQuantizationTests(unittest.TestCase):
    def test_complex_coefficients_reach_target_and_decode_both_bits(self):
        coefficients = np.array([0.2 + 0.3j, -0.6 + 0.2j])
        original = coefficients.copy()
        self.assertAlmostEqual(np.vdot(coefficients, coefficients).real, 0.53)
        for bit, target in ((0, 0.45), (1, 0.55)):
            with self.subTest(bit=bit):
                modified = embed_bit(coefficients, bit)
                self.assertAlmostEqual(np.vdot(modified, modified).real, target)
                self.assertEqual(extract_bit(modified), bit)
                np.testing.assert_allclose(
                    modified / coefficients, np.sqrt(target / 0.53)
                )
        np.testing.assert_array_equal(coefficients, original)

    def test_other_quantization_step_with_real_coefficients(self):
        for bit in (0, 1):
            with self.subTest(bit=bit):
                modified = embed_bit([0.1, -0.1], bit, delta=0.125)
                self.assertEqual(extract_bit(modified, delta=0.125), bit)

    def test_zero_energy_vector_cannot_be_scaled_to_target(self):
        with self.assertRaisesRegex(ValueError, "zero-energy"):
            embed_bit(np.zeros(16), 1)

    def test_invalid_bits_and_steps_are_rejected(self):
        with self.assertRaises(ValueError):
            embed_bit([1], 2)
        for delta in (0, -0.2, np.inf, np.nan):
            with self.subTest(delta=delta):
                with self.assertRaises(ValueError):
                    extract_bit([1], delta=delta)
