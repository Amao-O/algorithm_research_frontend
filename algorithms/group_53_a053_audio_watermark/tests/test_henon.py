import unittest

import numpy as np

from src.henon import HenonKey, mask_watermark


class HenonTests(unittest.TestCase):
    def test_reference_mask_with_both_modifiers_enabled(self):
        key = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
        expected_mask = [1, 1, 0, 0, 0, 1, 1, 1]
        np.testing.assert_array_equal(mask_watermark([0] * 8, key), expected_mask)

    def test_same_key_recovers_original_bits(self):
        key = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
        original = [0, 1, 1, 0, 1, 1, 0, 0]
        masked = mask_watermark(original, key)
        self.assertFalse(np.array_equal(masked, original))
        np.testing.assert_array_equal(mask_watermark(masked, key), original)

    def test_values_equal_to_threshold_are_one(self):
        key = HenonKey(a=1.4, b=0, c=0, d=0, x0=0, y0=0)
        np.testing.assert_array_equal(mask_watermark([0, 1, 0], key), [1, 0, 1])

    def test_invalid_bits_and_key_are_rejected(self):
        key = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
        with self.assertRaises(ValueError):
            mask_watermark([0, 2], key)
        with self.assertRaises(ValueError):
            HenonKey(a=1.4, b=0.3, c=0.9, d=0.4, x0=0.3, y0=0.5)
