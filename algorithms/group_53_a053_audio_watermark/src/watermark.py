"""Single-process A053 embedding and blind extraction for 44.1 kHz WAV."""

from operator import index

import numpy as np
from scipy.io import wavfile

from .dtcwt_transform import (
    FRAME_SIZE,
    LOWPASS_SIZE,
    complex_lowpass,
    forward_frame,
    inverse_frame,
)
from .frct import frct_matrix
from .henon import HenonKey, mask_watermark
from .quantization import _step, embed_bit, extract_bit


SAMPLE_RATE = 44_100
_PCM_SCALE = 32_768


def _read_wav(path) -> np.ndarray:
    rate, pcm = wavfile.read(path)
    if (
        rate != SAMPLE_RATE
        or pcm.ndim != 1
        or pcm.dtype.kind != "i"
        or pcm.dtype.itemsize != 2
    ):
        raise ValueError("expected a mono 44,100 Hz PCM16 WAV")
    return pcm.astype(np.float64) / _PCM_SCALE


def _check_capacity(bit_count: int, samples: np.ndarray):
    if not 1 <= bit_count <= samples.size // FRAME_SIZE:
        raise ValueError("watermark length exceeds WAV frame capacity or is empty")


def _write_wav(destination, samples):
    pcm = np.rint(samples * _PCM_SCALE)
    if np.any((pcm < -_PCM_SCALE) | (pcm >= _PCM_SCALE)):
        raise ValueError("watermark exceeds PCM16 range; use an input with more headroom")
    wavfile.write(destination, SAMPLE_RATE, pcm.astype(np.int16))


def _frame_coefficients(frame: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return matrix @ complex_lowpass(forward_frame(frame))


def _calibrate_frame(frame, pyramid, lowpass, matrix, bit, delta, margin):
    """Choose a low-pass gain using the analysis of the final PCM frame."""
    coefficients = matrix @ lowpass
    energy = float(np.vdot(coefficients, coefficients).real)
    lower = bit * delta / 2
    upper = lower + delta / 2
    remainder = energy % delta
    if lower + margin <= remainder < upper - margin:
        return frame

    # Reanalysis of the cropped frame is linear before PCM rounding.
    # Changing the low-pass gain by t changes its coefficients by t * direction.
    detail_only = inverse_frame(pyramid, lowpass=np.zeros_like(lowpass))
    response = frame - detail_only
    direction = _frame_coefficients(response, matrix)
    quadratic = float(np.vdot(direction, direction).real)
    if quadratic == 0:
        raise ValueError("cannot calibrate a zero-energy low-pass response")
    linear = float(np.vdot(direction, coefficients).real)

    bin_start = energy - remainder
    gain_changes = []
    for start in (bin_start - delta, bin_start, bin_start + delta):
        if start < 0:
            continue
        first = start + lower + margin
        last = start + upper - margin
        for target in (np.clip(energy, first, last), (first + last) / 2):
            discriminant = linear**2 + quadratic * (target - energy)
            if discriminant >= 0:
                root = np.sqrt(discriminant)
                gain_changes.extend(((-linear + root) / quadratic, (-linear - root) / quadratic))

    for change in sorted(gain_changes, key=abs):
        if change < -1:
            continue
        pcm = np.rint((frame + change * response) * _PCM_SCALE)
        if np.any((pcm < -_PCM_SCALE) | (pcm >= _PCM_SCALE)):
            continue
        candidate = pcm / _PCM_SCALE
        if extract_bit(_frame_coefficients(candidate, matrix), delta) == bit:
            return candidate
    raise ValueError("cannot reach the target bit with a PCM16 low-pass gain")


def _embed_frames(frames, bits, matrix, delta, margin):
    marked = np.empty_like(frames)
    inverse = matrix.conj().T
    for i, (frame, bit) in enumerate(zip(frames, bits, strict=True)):
        pyramid = forward_frame(frame)
        lowpass = complex_lowpass(pyramid)
        try:
            if margin is None:
                modified = embed_bit(matrix @ lowpass, bit, delta)
                marked[i] = inverse_frame(pyramid, lowpass=inverse @ modified)
            else:
                marked[i] = _calibrate_frame(frame, pyramid, lowpass, matrix, bit, delta, margin)
        except ValueError as exc:
            raise ValueError(f"cannot embed watermark in frame {i}: {exc}") from exc
    return marked


def _extract_frames(frames, matrix, delta):
    return np.fromiter(
        (extract_bit(_frame_coefficients(frame, matrix), delta) for frame in frames),
        dtype=np.uint8,
        count=len(frames),
    )


def embed_wav(
    source,
    destination,
    bits,
    key: HenonKey,
    *,
    alpha: float = 0.2,
    delta: float = 0.2,
    a1: float = 0.16,
    calibrate: bool = False,
    calibration_margin: float = 0.025,
) -> None:
    """Write one bit per frame, with an optional margin expressed as a fraction of delta."""
    samples = _read_wav(source)
    encrypted = mask_watermark(bits, key)
    _check_capacity(encrypted.size, samples)
    delta = _step(delta)
    if calibrate and not 0 <= calibration_margin < 0.25:
        raise ValueError("calibration_margin must be in [0, 0.25)")
    margin = delta * calibration_margin if calibrate else None
    matrix = frct_matrix(LOWPASS_SIZE, alpha, a1=a1)
    end = encrypted.size * FRAME_SIZE
    frames = samples[:end].reshape(-1, FRAME_SIZE)
    samples[:end] = _embed_frames(frames, encrypted, matrix, delta, margin).ravel()
    _write_wav(destination, samples)


def extract_wav(
    source,
    bit_count: int,
    key: HenonKey,
    *,
    alpha: float = 0.2,
    delta: float = 0.2,
    a1: float = 0.16,
) -> np.ndarray:
    """Read bits using the marked WAV, payload length and algorithm parameters."""
    samples = _read_wav(source)
    bit_count = index(bit_count)
    _check_capacity(bit_count, samples)
    delta = _step(delta)
    matrix = frct_matrix(LOWPASS_SIZE, alpha, a1=a1)
    frames = samples[: bit_count * FRAME_SIZE].reshape(-1, FRAME_SIZE)
    encrypted = _extract_frames(frames, matrix, delta)
    return mask_watermark(encrypted, key)
