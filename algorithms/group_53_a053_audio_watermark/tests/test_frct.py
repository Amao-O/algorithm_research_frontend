import unittest

import numpy as np

from src.frct import _orthonormal_charlier, frct_matrix


class FractionalCharlierTests(unittest.TestCase):
    def test_weighted_recurrence_and_row_qr_match_published_size_four_table(self):
        expected = [
            [0.980199, 0.196042, 0.027724, 0.003083],
            [0.19604, -0.94101, -0.2719, -0.04624],
            [0.027724, -0.2717, 0.904708, 0.326975],
            [0.003201, -0.04738, 0.326811, -0.9439],
        ]
        # Table 2 lists the orthonormalized vectors as columns.
        np.testing.assert_allclose(
            _orthonormal_charlier(4, 0.04).T, expected, atol=5e-6, rtol=0
        )

    def test_size_two_fractional_matrix_matches_published_sign_projectors(self):
        integer = np.array([[0.990148, 0.140028], [0.140028, -0.99015]])
        identity = np.eye(2)
        alpha = 0.2
        expected = (identity + integer) / 2 + np.exp(-1j * np.pi * alpha) * (
            identity - integer
        ) / 2
        np.testing.assert_allclose(
            frct_matrix(2, alpha, a1=0.02), expected, atol=2e-6, rtol=0
        )

    def test_order_zero_additivity_and_inverse_at_audio_size(self):
        size = 16
        a1 = 0.16
        forward = frct_matrix(size, 0.2, a1=a1)
        inverse = frct_matrix(size, -0.2, a1=a1)
        vector = np.arange(size) / size + 1j * np.linspace(0, 1, size)
        np.testing.assert_allclose(frct_matrix(size, 0, a1=a1), np.eye(size), atol=1e-12)
        np.testing.assert_allclose(inverse @ (forward @ vector), vector, atol=1e-12)
        np.testing.assert_allclose(
            forward @ frct_matrix(size, 0.3, a1=a1),
            frct_matrix(size, 0.5, a1=a1),
            atol=1e-12,
        )
