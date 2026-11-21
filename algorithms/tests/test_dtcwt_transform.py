import unittest

import numpy as np

from src.dtcwt_transform import (
    FRAME_SIZE,
    LEVELS,
    complex_lowpass,
    forward_frame,
    inverse_frame,
)


class FrameTransformTests(unittest.TestCase):
    def test_complex_lowpass_can_be_repacked_without_changing_the_frame(self):
        frame = np.random.default_rng(53).uniform(-1, 1, FRAME_SIZE)
        pyramid = forward_frame(frame)
        approximation = complex_lowpass(pyramid)
        self.assertEqual(approximation.shape, (16,))
        np.testing.assert_array_equal(approximation.real, pyramid.lowpass[::2, 0])
        np.testing.assert_array_equal(approximation.imag, pyramid.lowpass[1::2, 0])
        np.testing.assert_allclose(
            inverse_frame(pyramid, lowpass=approximation), frame, rtol=0, atol=1e-12
        )

    def test_replacing_lowpass_changes_output_without_mutating_the_pyramid(self):
        frame = np.full(FRAME_SIZE, 0.5)
        pyramid = forward_frame(frame)
        without_lowpass = inverse_frame(pyramid, lowpass=np.zeros(16))
        # The published reference filter coefficients leave a small DC residual.
        np.testing.assert_allclose(without_lowpass, 0, rtol=0, atol=1e-7)
        np.testing.assert_allclose(inverse_frame(pyramid), frame, rtol=0, atol=1e-12)

    def test_five_level_roundtrip_preserves_frame_and_boundary_samples(self):
        impulse = np.zeros(FRAME_SIZE)
        impulse[[0, -1]] = [1, -0.5]
        random_frame = np.random.default_rng(53).uniform(-1, 1, FRAME_SIZE)
        for frame in (impulse, random_frame, np.zeros(FRAME_SIZE)):
            with self.subTest(first_sample=frame[0]):
                pyramid = forward_frame(frame)
                self.assertEqual(len(pyramid.highpasses), LEVELS)
                reconstructed = inverse_frame(pyramid)
                self.assertEqual(reconstructed.shape, frame.shape)
                np.testing.assert_allclose(reconstructed, frame, rtol=0, atol=1e-12)

    def test_invalid_frames_are_rejected(self):
        for invalid in (
            np.zeros(FRAME_SIZE - 1),
            np.zeros((FRAME_SIZE, 1)),
            np.zeros(FRAME_SIZE, dtype=complex),
            np.full(FRAME_SIZE, np.nan),
        ):
            with self.subTest(shape=invalid.shape, dtype=invalid.dtype):
                with self.assertRaises(ValueError):
                    forward_frame(invalid)
