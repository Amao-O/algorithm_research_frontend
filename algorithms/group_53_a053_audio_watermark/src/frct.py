"""Fractional Charlier matrices for the A053 reproduction."""

import numpy as np
from scipy.linalg import qr
from scipy.special import gammaln


def _orthonormal_charlier(size: int, a1: float) -> np.ndarray:
    """Evaluate the weighted recurrence and orthonormalize its rows."""
    x = np.arange(size)
    rows = np.empty((size, size))
    rows[0] = np.exp((-a1 + x * np.log(a1) - gammaln(x + 1)) / 2)
    if size > 1:
        rows[1] = (a1 - x) * rows[0] / np.sqrt(a1)
    for n in range(2, size):
        rows[n] = (
            (a1 + n - 1 - x) / np.sqrt(a1 * n) * rows[n - 1]
            - np.sqrt((n - 1) / n) * rows[n - 2]
        )

    # QR on the transpose is row Gram–Schmidt. Keep the original row signs.
    columns, triangular = np.linalg.qr(rows.T)
    diagonal = np.diag(triangular)
    if np.any(np.abs(diagonal) < np.finfo(float).eps * size):
        raise ValueError("truncated Charlier matrix is numerically rank deficient")
    return (columns * np.sign(diagonal)).T


def frct_matrix(size: int, alpha: float, *, a1: float) -> np.ndarray:
    """Build the finite FrCT matrix in the order of equations (37) and (41)."""
    if size < 1 or not np.isfinite(alpha) or not np.isfinite(a1) or a1 <= 0:
        raise ValueError("FrCT requires positive size and a1 and finite parameters")

    rows = _orthonormal_charlier(size, a1)
    # Row orthonormalization alone need not preserve symmetry. The signs of
    # the symmetric part yield the nearest symmetric orthogonal matrix.
    eigenvalues, vectors = np.linalg.eigh((rows + rows.T) / 2)
    positive = eigenvalues > 0
    if (
        np.min(np.abs(eigenvalues)) < 1e-12
        or np.count_nonzero(positive) != (size + 1) // 2
    ):
        raise ValueError("Charlier matrix does not have the expected sign subspaces")

    basis = np.empty_like(vectors)
    for parity, subspace in enumerate((vectors[:, positive], vectors[:, ~positive])):
        rank = subspace.shape[1]
        if rank:
            # Repeated eigenvalues leave the basis unspecified. Pivoted QR of
            # projected coordinate axes chooses a basis within that subspace.
            projector = subspace @ subspace.T
            columns, _, _ = qr(projector, pivoting=True)
            basis[:, parity::2] = columns[:, :rank]

    phases = np.exp(-1j * np.pi * np.remainder(alpha, 2) * np.arange(size))
    return (basis * phases) @ basis.T
