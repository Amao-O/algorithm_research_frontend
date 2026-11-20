"""Five-level frame transform using the dtcwt reference filter bank."""

import numpy as np
from dtcwt.numpy import Pyramid, Transform1d


FRAME_SIZE = 486
LEVELS = 5
_PAD_WIDTH = 13
LOWPASS_SIZE = (FRAME_SIZE + 2 * _PAD_WIDTH) // 2**LEVELS
_TRANSFORM = Transform1d(biort="near_sym_a", qshift="qshift_a")


def forward_frame(frame) -> Pyramid:
    """Symmetrically extend one real 486-sample frame to 512 samples."""
    samples = np.asarray(frame)
    if samples.shape != (FRAME_SIZE,) or samples.dtype.kind not in "fiu":
        raise ValueError(f"expected {FRAME_SIZE} real audio samples in one dimension")
    samples = samples.astype(np.float64, copy=False)
    if not np.all(np.isfinite(samples)):
        raise ValueError("audio samples must be finite")
    padded = np.pad(samples, _PAD_WIDTH, mode="symmetric")
    return _TRANSFORM.forward(padded, nlevels=LEVELS)


def complex_lowpass(pyramid: Pyramid) -> np.ndarray:
    """Pair the even and odd low-pass rows as real and imaginary parts."""
    lowpass = pyramid.lowpass[:, 0]
    return lowpass[::2] + 1j * lowpass[1::2]


def inverse_frame(pyramid: Pyramid, *, lowpass=None) -> np.ndarray:
    """Reconstruct a frame, optionally replacing its complex low-pass band."""
    if lowpass is not None:
        values = np.asarray(lowpass)
        expected = (pyramid.lowpass.shape[0] // 2,)
        if values.shape != expected or values.dtype.kind not in "fiuc":
            raise ValueError(f"expected complex low-pass coefficients of shape {expected}")
        if not np.all(np.isfinite(values)):
            raise ValueError("low-pass coefficients must be finite")
        interleaved = np.empty_like(pyramid.lowpass)
        interleaved[::2, 0] = values.real
        interleaved[1::2, 0] = values.imag
        pyramid = Pyramid(interleaved, pyramid.highpasses)

    padded = _TRANSFORM.inverse(pyramid).ravel()
    if padded.size != FRAME_SIZE + 2 * _PAD_WIDTH:
        raise ValueError("unexpected reconstructed frame length")
    return padded[_PAD_WIDTH : _PAD_WIDTH + FRAME_SIZE]
