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
from .quantization import embed_bit, extract_bit


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


def embed_wav(
    source,
    destination,
    bits,
    key: HenonKey,
    *,
    alpha: float = 0.2,
    delta: float = 0.2,
    a1: float = 0.16,
) -> None:
    """Write a PCM16 WAV with one bit per frame, preserving unused samples."""
    samples = _read_wav(source)
    encrypted = mask_watermark(bits, key)
    _check_capacity(encrypted.size, samples)
    matrix = frct_matrix(LOWPASS_SIZE, alpha, a1=a1)
    inverse = matrix.conj().T
    for i, bit in enumerate(encrypted):
        window = slice(i * FRAME_SIZE, (i + 1) * FRAME_SIZE)
        pyramid = forward_frame(samples[window])
        lowpass = complex_lowpass(pyramid)
        try:
            modified = embed_bit(matrix @ lowpass, bit, delta)
        except ValueError as exc:
            raise ValueError(f"cannot embed watermark in frame {i}: {exc}") from exc
        samples[window] = inverse_frame(pyramid, lowpass=inverse @ modified)

    pcm = np.rint(samples * _PCM_SCALE)
    if np.any((pcm < -_PCM_SCALE) | (pcm >= _PCM_SCALE)):
        raise ValueError("watermark exceeds PCM16 range; use an input with more headroom")
    wavfile.write(destination, SAMPLE_RATE, pcm.astype(np.int16))


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
    matrix = frct_matrix(LOWPASS_SIZE, alpha, a1=a1)
    encrypted = np.empty(bit_count, dtype=np.uint8)
    for i in range(bit_count):
        window = slice(i * FRAME_SIZE, (i + 1) * FRAME_SIZE)
        lowpass = complex_lowpass(forward_frame(samples[window]))
        encrypted[i] = extract_bit(matrix @ lowpass, delta)
    return mask_watermark(encrypted, key)
