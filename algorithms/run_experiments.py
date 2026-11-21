"""Compare A053 embedding modes on preprocessed 44.1 kHz PCM16 WAV audio."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from scipy.io import wavfile

from src.dtcwt_transform import FRAME_SIZE
from src.henon import HenonKey
from src.watermark import embed_wav, extract_wav


_MODES = {"baseline": None, "margin_0025": 0.025, "margin_0200": 0.2}
_KEY = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
_ATTACKS = ("awgn_30_db", "mp3_128_kbps", "right_shift_5_samples")


def _simulate_attack(source, output, attack, rate, pcm):
    if attack == "awgn_30_db":
        signal = pcm.astype(np.float64)
        noise = np.random.default_rng(532).normal(size=pcm.size)
        noise *= np.linalg.norm(signal) / (10**1.5 * np.linalg.norm(noise))
        attacked = np.clip(np.rint(signal + noise), -32768, 32767).astype(np.int16)
        wavfile.write(output, rate, attacked)
    elif attack == "right_shift_5_samples":
        shifted = np.zeros_like(pcm)
        shifted[5:] = pcm[:-5]
        wavfile.write(output, rate, shifted)
    elif attack == "mp3_128_kbps":
        encoded = output.with_suffix(".mp3")
        ffmpeg = ["ffmpeg", "-nostdin", "-v", "error"]
        subprocess.run(
            [*ffmpeg, "-i", str(source), "-c:a", "libmp3lame", "-b:a", "128k", str(encoded)],
            check=True,
        )
        subprocess.run([*ffmpeg, "-i", str(encoded), "-c:a", "pcm_s16le", str(output)], check=True)
        decoded_rate, decoded = wavfile.read(output)
        if decoded_rate != rate or decoded.shape != pcm.shape:
            raise ValueError("MP3 roundtrip changed the sample rate or frame count")


def _bit_errors(path, bits):
    restored = extract_wav(path, bits.size, _KEY)
    errors = int(np.count_nonzero(restored != bits))
    return {"wrong_bits": errors, "ber_percent": 100 * errors / bits.size}


def _run_case(job):
    source, output_dir, mode = job
    margin = _MODES[mode]
    output = output_dir / f"{source.stem}_{mode}.wav"
    result = {
        "track": source.name,
        "mode": mode,
        "calibration_margin": margin,
    }
    try:
        rate, pcm = wavfile.read(source)
        bit_count = pcm.shape[0] // FRAME_SIZE
        bits = np.random.default_rng(53).integers(0, 2, size=bit_count, dtype=np.uint8)
        result.update(duration_seconds=pcm.shape[0] / rate, watermark_bits=bit_count)
        start = perf_counter()
        options = {} if margin is None else {"calibrate": True, "calibration_margin": margin}
        embed_wav(source, output, bits, _KEY, **options)
        result["embedding_seconds"] = perf_counter() - start
        encoded_rate, marked = wavfile.read(output)
        if encoded_rate != rate or marked.shape != pcm.shape or marked.dtype != pcm.dtype:
            raise ValueError("embedding changed the WAV format or sample count")
        reference = pcm.astype(np.float64)
        diff = reference - marked
        distortion = np.dot(diff, diff)
        result["snr_db"] = (
            float(10 * np.log10(np.dot(reference, reference) / distortion))
            if distortion
            else None
        )
        result["output_wav"] = output.name
        result.update(_bit_errors(output, bits))
    except (ValueError, OSError) as exc:
        result["error"] = str(exc)
        return result

    result["attacks"] = {}
    with TemporaryDirectory() as scratch:
        for attack in _ATTACKS:
            attacked = Path(scratch) / f"{attack}.wav"
            try:
                _simulate_attack(output, attacked, attack, rate, marked)
                result["attacks"][attack] = _bit_errors(attacked, bits)
            except (ValueError, OSError, subprocess.CalledProcessError) as exc:
                result["attacks"][attack] = {"error": str(exc)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", nargs="+", type=Path, help="preprocessed PCM16 WAV files")
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if len({path.stem for path in args.wav}) != len(args.wav):
        parser.error("input WAV names must be distinct")
    args.output.mkdir(parents=True, exist_ok=False)
    jobs = [(path, args.output, mode) for path in args.wav for mode in _MODES]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(_run_case, jobs):
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    report = {
        "watermark_seed": 53,
        "awgn_seed": 532,
        "alpha": 0.2,
        "delta": 0.2,
        "a1": 0.16,
        "results": results,
    }
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return int(any(
        "error" in case or any("error" in attack for attack in case.get("attacks", {}).values())
        for case in results
    ))


if __name__ == "__main__":
    raise SystemExit(main())
