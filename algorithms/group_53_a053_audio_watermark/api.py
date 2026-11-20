"""Local HTTP adapter for the algorithm research platform."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
from struct import error as StructError
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from time import time
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import numpy as np

from src.henon import HenonKey
from src.watermark import embed_wav, extract_wav


METHOD_ID = "group_53_a053_audio_watermark"
MAX_UPLOAD_BYTES = 6 * 1024**2
MAX_BIT_COUNT = 5444
RESULT_TTL_SECONDS = 3600
_KEY = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
_SLOT = BoundedSemaphore(1)
_RESULTS = {
    "watermarked.wav": ("audio", "带水印音频", "audio/wav"),
    "report.json": ("json", "水印报告", "application/json"),
}
_LOCAL_ORIGINS = ",".join(
    f"http://{host}:{port}"
    for host in ("127.0.0.1", "localhost")
    for port in (5173, 4173)
)


@asynccontextmanager
async def lifespan(app):
    with TemporaryDirectory(prefix="a053-results-") as folder:
        app.state.results = Path(folder)
        yield


app = FastAPI(title="A053 音频水印", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("A053_ALLOWED_ORIGINS", _LOCAL_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


def _error(status, message):
    return JSONResponse({"error": message}, status_code=status)


@app.exception_handler(RequestValidationError)
async def invalid_form(_request, _error_details):
    return _error(422, "请提交音频文件、method_id 和 JSON 参数。")


def _parameters(raw):
    try:
        fields = json.loads(raw)
    except ValueError as exc:
        raise ValueError("parameters 必须是 JSON 对象。") from exc
    if not isinstance(fields, dict) or fields.keys() - {"mode", "watermark", "bit_count"}:
        raise ValueError("parameters 只接受 mode、watermark 和 bit_count。")
    mode = fields.get("mode", "embed")
    if mode == "embed":
        watermark = fields.get("watermark", "A053")
        if not isinstance(watermark, str) or not watermark.strip() or len(watermark) > 16:
            raise ValueError("水印文字需要 1–16 个字符。")
        return mode, np.unpackbits(np.frombuffer(watermark.encode("utf-8"), dtype=np.uint8))
    if mode == "extract":
        bit_count = fields.get("bit_count", 32)
        if type(bit_count) is not int or not 1 <= bit_count <= MAX_BIT_COUNT:
            raise ValueError(f"提取位数必须是 1–{MAX_BIT_COUNT} 的整数。")
        return mode, bit_count
    raise ValueError("mode 必须为 embed 或 extract。")


def _prune(results):
    cutoff = time() - RESULT_TTL_SECONDS
    for folder in results.iterdir():
        if folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder)


def _artifact(run_id, name):
    kind, label, _ = _RESULTS[name]
    return {"kind": kind, "label": label, "filename": name, "url": f"files/{run_id}/{name}"}


@app.post("/process")
def process(
    request: Request,
    audio: UploadFile = File(),
    method_id: str = Form(),
    parameters: str = Form(),
):
    if method_id != METHOD_ID:
        return _error(400, "method_id 与本算法不匹配。")
    try:
        mode, payload = _parameters(parameters)
    except ValueError as exc:
        return _error(422, str(exc))
    if not _SLOT.acquire(blocking=False):
        return _error(503, "当前有音频正在处理，请稍后重试。")

    try:
        uploaded = audio.file.read(MAX_UPLOAD_BYTES + 1)
        if len(uploaded) > MAX_UPLOAD_BYTES:
            return _error(413, "音频文件不得超过 6 MB。")
        results = request.app.state.results
        _prune(results)
        run_id = uuid4()
        folder = results / str(run_id)
        folder.mkdir()
        try:
            with TemporaryDirectory(prefix="a053-input-") as scratch:
                source = Path(scratch) / "input.wav"
                source.write_bytes(uploaded)
                artifacts = []
                if mode == "embed":
                    embed_wav(
                        source, folder / "watermarked.wav", payload, _KEY,
                        calibrate=True, calibration_margin=0.20,
                    )
                    report = {"mode": mode, "bit_count": int(payload.size), "calibration_margin": 0.20}
                    artifacts.append(_artifact(run_id, "watermarked.wav"))
                    message = f"已嵌入 {payload.size} 位水印。提取时请使用相同位数。"
                else:
                    recovered = extract_wav(source, payload, _KEY)
                    decoded = None
                    if payload % 8 == 0:
                        try:
                            decoded = np.packbits(recovered).tobytes().decode("utf-8")
                        except UnicodeDecodeError:
                            pass
                    report = {
                        "mode": mode, "bit_count": payload,
                        "bits": recovered.tolist(), "watermark_text": decoded,
                    }
                    message = f"已提取 {payload} 位水印，结果见报告。"
            (folder / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except (EOFError, StructError):
            shutil.rmtree(folder, ignore_errors=True)
            return _error(422, "WAV 文件不完整。请重新导出音频后再上传。")
        except ValueError as exc:
            shutil.rmtree(folder, ignore_errors=True)
            return _error(422, f"请检查音频格式、水印位数和音量。{exc}")
        except OSError:
            shutil.rmtree(folder, ignore_errors=True)
            return _error(500, "暂时无法保存处理结果。")
        return {"message": message, "artifacts": [*artifacts, _artifact(run_id, "report.json")]}
    finally:
        _SLOT.release()


@app.get("/files/{run_id}/{name}")
def result_file(request: Request, run_id: UUID, name: str):
    if name not in _RESULTS:
        return _error(404, "找不到结果文件。")
    folder = request.app.state.results / str(run_id)
    path = folder / name
    if not path.is_file() or time() - folder.stat().st_mtime >= RESULT_TTL_SECONDS:
        return _error(404, "找不到结果文件，或结果已过期。")
    return FileResponse(path, media_type=_RESULTS[name][2], headers={"Cache-Control": "no-store"})
