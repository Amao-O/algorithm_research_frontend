"""Candidate squared-energy quantization for a single watermark bit."""

import numpy as np


def _coefficients_and_energy(coefficients):
    values = np.asarray(coefficients)
    if values.ndim != 1 or not values.size or values.dtype.kind not in "fiuc":
        raise ValueError("expected a nonempty one-dimensional coefficient vector")
    dtype = np.complex128 if np.iscomplexobj(values) else np.float64
    values = values.astype(dtype, copy=False)
    if not np.all(np.isfinite(values)):
        raise ValueError("coefficients must be finite")
    energy = float(np.vdot(values, values).real)
    if not np.isfinite(energy):
        raise ValueError("coefficient energy exceeds floating-point range")
    return values, energy


def _step(delta: float) -> float:
    delta = float(delta)
    if not np.isfinite(delta) or delta <= 0:
        raise ValueError("delta must be finite and positive")
    return delta


def embed_bit(coefficients, bit: int, delta: float = 0.2) -> np.ndarray:
    """Scale the vector to a quarter-bin or three-quarter-bin energy."""
    if bit not in (0, 1):
        raise ValueError("bit must be 0 or 1")
    delta = _step(delta)
    values, energy = _coefficients_and_energy(coefficients)
    if energy == 0:
        raise ValueError("cannot embed by scaling a zero-energy vector")
    remainder = energy % delta
    offset = delta * (0.75 if bit else 0.25)
    target = energy + (offset - remainder)
    if not np.isfinite(target) or target <= 0 or np.spacing(target) >= delta / 4:
        raise ValueError("quantized energy cannot be represented at this step")
    return (values / np.sqrt(energy)) * np.sqrt(target)


def extract_bit(coefficients, delta: float = 0.2) -> int:
    """Decode the bit from the energy position within its quantization bin."""
    delta = _step(delta)
    _, energy = _coefficients_and_energy(coefficients)
    return int(energy % delta >= delta / 2)
