"""Run the A053 no-attack WAV benchmark with MPI and record output checksums."""

import argparse
import hashlib
import json
from pathlib import Path

from mpi4py import MPI
import numpy as np

from .dtcwt_transform import FRAME_SIZE, LOWPASS_SIZE
from .frct import frct_matrix
from .henon import HenonKey, mask_watermark
from .watermark import _embed_frames, _extract_frames, _read_wav, _write_wav


def _root_call(comm, operation):
    """Run root-only I/O and communicate failure before the next collective."""
    result, error = None, None
    if comm.rank == 0:
        try:
            result = operation()
        except (ValueError, OSError) as exc:
            error = str(exc)
    error = comm.bcast(error, root=0)
    if error is not None:
        raise ValueError(error)
    return result


def _process_chunks(comm, chunks, process):
    chunk = comm.scatter(chunks, root=0)
    try:
        value = process(chunk)
        error = None
    except ValueError as exc:
        value, error = None, f"rank {comm.rank}: {exc}"
    outputs = comm.gather((value, error), root=0)

    def combine():
        for _, failure in outputs:
            if failure is not None:
                raise ValueError(failure)
        return np.concatenate([output for output, _ in outputs])

    return _root_call(comm, combine)


def _checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--output-wav", type=Path, required=True)
    parser.add_argument("--calibration-margin", type=float, default=None)
    args = parser.parse_args()
    if args.wav.resolve() == args.output_wav.resolve():
        parser.error("input and output WAV paths must differ")
    if args.calibration_margin is not None and not 0 <= args.calibration_margin < 0.25:
        parser.error("--calibration-margin must be in [0, 0.25)")

    comm = MPI.COMM_WORLD
    key = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
    delta = 0.2
    margin = None if args.calibration_margin is None else delta * args.calibration_margin
    matrix = frct_matrix(LOWPASS_SIZE, 0.2, a1=0.16)
    samples = _root_call(comm, lambda: _read_wav(args.wav))
    bit_count = comm.bcast(samples.size // FRAME_SIZE if comm.rank == 0 else None, root=0)
    if bit_count == 0:
        raise ValueError("input WAV has no complete watermark frames")
    end = bit_count * FRAME_SIZE

    comm.Barrier()
    start = MPI.Wtime()

    def prepare_embedding():
        bits = np.random.default_rng(53).integers(0, 2, size=bit_count, dtype=np.uint8)
        encrypted = mask_watermark(bits, key)
        frame_chunks = np.array_split(samples[:end].reshape(-1, FRAME_SIZE), comm.size)
        jobs = list(zip(frame_chunks, np.array_split(encrypted, comm.size), strict=True))
        return bits, jobs

    preparation = _root_call(comm, prepare_embedding)
    bits, jobs = preparation if comm.rank == 0 else (None, None)
    marked = _process_chunks(
        comm, jobs, lambda chunk: _embed_frames(*chunk, matrix, delta, margin)
    )
    embed_seconds = MPI.Wtime() - start

    def write_marked():
        samples[:end] = marked.ravel()
        _write_wav(args.output_wav, samples)

    _root_call(comm, write_marked)
    del marked
    output = _root_call(comm, lambda: _read_wav(args.output_wav))
    comm.Barrier()
    start = MPI.Wtime()
    jobs = _root_call(
        comm, lambda: np.array_split(output[:end].reshape(-1, FRAME_SIZE), comm.size)
    )
    extracted = _process_chunks(comm, jobs, lambda chunk: _extract_frames(chunk, matrix, delta))
    if comm.rank == 0:
        restored = mask_watermark(extracted, key)
        extract_seconds = MPI.Wtime() - start
        wrong = int(np.count_nonzero(restored != bits))
        print(json.dumps({
            "processes": comm.size,
            "calibration_margin": args.calibration_margin,
            "watermark_bits": bit_count,
            "wrong_bits": wrong,
            "ber_percent": 100 * wrong / bit_count,
            "embedding_seconds": embed_seconds,
            "extraction_seconds": extract_seconds,
            "output_sha256": _checksum(args.output_wav),
        }))


if __name__ == "__main__":
    main()
