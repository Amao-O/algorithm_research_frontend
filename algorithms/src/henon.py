"""Modified Henon watermark masking from equations (7) and (9)–(11)."""

from dataclasses import dataclass
from math import cos, isfinite, sin

import numpy as np


@dataclass(frozen=True)
class HenonKey:
    a: float
    b: float
    c: float
    d: float
    x0: float
    y0: float

    def __post_init__(self):
        if not 0.54 <= self.a <= 2 or not 0 <= self.b <= 1:
            raise ValueError("Henon requires 0.54 <= a <= 2 and 0 <= b <= 1")
        if not 0 <= self.c <= 0.8 or not 0 <= self.d <= 0.8:
            raise ValueError("Henon requires c and d to be in [0, 0.8]")
        if not isfinite(self.x0) or not isfinite(self.y0):
            raise ValueError("Henon initial state must be finite")


def mask_watermark(bits, key: HenonKey) -> np.ndarray:
    """Apply the same XOR mask to embed or recover a full binary watermark."""
    values = np.asarray(bits)
    if (
        values.ndim != 1
        or not values.size
        or values.dtype.kind not in "biu"
        or not np.all((values == 0) | (values == 1))
    ):
        raise ValueError("expected a nonempty vector of binary watermark bits")

    x, y = float(key.x0), float(key.y0)
    sequence = np.empty(values.size, dtype=np.float64)
    # Treat the supplied state as the seed before the first update at i = 0.
    for i in range(values.size):
        x, y = (
            1 - key.a * (1 - key.c * abs(cos(i))) * x * x + y,
            key.b * (1 - key.d * abs(sin(y))) * x,
        )
        if not isfinite(x) or not isfinite(y):
            raise ValueError("Henon orbit diverged for this key")
        sequence[i] = y

    mask = sequence >= sequence.mean()
    return np.bitwise_xor(values.astype(np.uint8), mask)
