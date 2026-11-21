from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from scipy.io import wavfile

from src.dtcwt_transform import FRAME_SIZE
from src.henon import HenonKey
from src.watermark import SAMPLE_RATE, embed_wav, extract_wav


KEY = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)


class WavWatermarkTests(unittest.TestCase):
    def test_calibration_recovers_bit_lost_after_frame_reanalysis(self):
        time = np.arange(FRAME_SIZE) / SAMPLE_RATE
        pcm = np.rint(32768 * 0.002 * np.sin(2 * np.pi * 880 * time)).astype(np.int16)
        bits = [0]  # A one-element Henon sequence masks this to bit 1.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "original.wav"
            default = folder / "default.wav"
            wavfile.write(source, SAMPLE_RATE, pcm)
            embed_wav(source, default, bits, KEY)
            self.assertEqual(extract_wav(default, 1, KEY).tolist(), [1])
            for margin in (0.025, 0.2):
                with self.subTest(margin=margin):
                    calibrated = folder / f"calibrated_{margin}.wav"
                    embed_wav(
                        source, calibrated, bits, KEY, calibrate=True, calibration_margin=margin
                    )
                    self.assertEqual(extract_wav(calibrated, 1, KEY).tolist(), bits)

    def test_pcm16_blind_roundtrip_and_unmodified_tail(self):
        rng = np.random.default_rng(53)
        bits = rng.integers(0, 2, size=128, dtype=np.uint8)
        embedded_length = bits.size * FRAME_SIZE
        time = np.arange(embedded_length + 57) / SAMPLE_RATE
        signal = 0.35 * np.sin(2 * np.pi * 440 * time)
        signal += 0.15 * np.sin(2 * np.pi * 880 * time)
        signal += 0.05 * rng.uniform(-1, 1, size=time.size)
        original = np.rint(32768 * signal).astype(np.int16)

        with TemporaryDirectory() as directory:
            source = Path(directory) / "original.wav"
            marked = Path(directory) / "marked.wav"
            wavfile.write(source, SAMPLE_RATE, original)
            embed_wav(source, marked, bits, KEY)
            rate, encoded = wavfile.read(marked)
            source.unlink()
            recovered = extract_wav(marked, bits.size, KEY)

        self.assertEqual(rate, SAMPLE_RATE)
        self.assertEqual(encoded.dtype, np.int16)
        self.assertEqual(encoded.size, original.size)
        self.assertFalse(np.array_equal(encoded, original))
        np.testing.assert_array_equal(encoded[embedded_length:], original[embedded_length:])
        np.testing.assert_array_equal(recovered, bits)

    def test_invalid_sample_rate_and_insufficient_capacity(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.wav"
            audio = np.full(FRAME_SIZE, 1000, dtype=np.int16)
            wavfile.write(path, 48_000, audio)
            with self.assertRaisesRegex(ValueError, "44,100"):
                extract_wav(path, 1, KEY)
            wavfile.write(path, SAMPLE_RATE, audio)
            with self.assertRaisesRegex(ValueError, "capacity"):
                embed_wav(path, Path(directory) / "marked.wav", [0, 1], KEY)
