"""
TikBypass Web — FastAPI backend
Video upload → bypass pipeline → download
"""

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ── Config ────────────────────────────────────────────────────────
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/tikbypass/uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/tikbypass/outputs"))
MAX_SIZE_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
KEEP_FILES_MIN = int(os.getenv("KEEP_FILES_MIN", "30"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(title="TikBypass", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Path to tikbypass tool (mounted in container)
TIKBYPASS_SCRIPT = Path(os.getenv("TIKBYPASS_SCRIPT", "/app/tikbypass.py"))


# ── Helpers ───────────────────────────────────────────────────────

def clean_old_files():
    """Remove uploads/outputs older than KEEP_FILES_MIN minutes."""
    cutoff = datetime.now().timestamp() - (KEEP_FILES_MIN * 60)
    for d in (UPLOAD_DIR, OUTPUT_DIR):
        for f in d.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)


def run_bypass(input_path: Path, output_path: Path, options: dict) -> tuple[bool, str]:
    """Run tikbypass.py with given options. Returns (success, log)."""
    cmd = [
        sys.executable, str(TIKBYPASS_SCRIPT),
        str(input_path),
        "-o", str(output_path),
        "--crf", str(options.get("crf", 18)),
        "--preset", options.get("preset", "medium"),
        "--fps", str(options.get("fps", 30)),
        "--width", str(options.get("width", 1080)),
        "--height", str(options.get("height", 1920)),
        "--maxrate", options.get("maxrate", "8M"),
        "--bufsize", options.get("bufsize", "16M"),
        "--audio-bitrate", options.get("audio_bitrate", "192k"),
        "--device", options.get("device", "iPhone15,2"),
        "--ios", options.get("ios", "16.4"),
        "--inflate-loops", str(options.get("inflate_loops", 5)),
    ]

    if options.get("no_sharpen"):
        cmd.append("--no-sharpen")
    if options.get("no_grain"):
        cmd.append("--no-grain")
    if options.get("no_faststart"):
        cmd.append("--no-faststart")
    if options.get("no_spoof"):
        cmd.append("--no-spoof")
    if options.get("no_inflate"):
        cmd.append("--no-inflate")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        log = result.stdout + "\n" + result.stderr
        return result.returncode == 0, log
    except subprocess.TimeoutExpired:
        return False, "Processing timed out (10 min limit)"
    except Exception as e:
        return False, str(e)


# ── Routes ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    crf: int = Form(18),
    preset: str = Form("medium"),
    fps: int = Form(30),
    width: int = Form(1080),
    height: int = Form(1920),
    maxrate: str = Form("8M"),
    bufsize: str = Form("16M"),
    audio_bitrate: str = Form("192k"),
    device: str = Form("iPhone15,2"),
    ios: str = Form("16.4"),
    inflate_loops: int = Form(5),
    no_sharpen: bool = Form(False),
    no_grain: bool = Form(False),
    no_faststart: bool = Form(False),
    no_spoof: bool = Form(False),
    no_inflate: bool = Form(False),
):
    # Validate
    if not file.filename or not file.filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
        return JSONResponse({"error": "Unsupported format. Use MP4, MOV, AVI, MKV, or WEBM."}, status_code=400)

    content_type = file.content_type or ""
    if "video" not in content_type and content_type not in ("application/octet-stream", ""):
        return JSONResponse({"error": f"Not a video file (detected: {content_type})"}, status_code=400)

    # Clean old files
    clean_old_files()

    # Save upload
    job_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix.lower()
    input_path = UPLOAD_DIR / f"{job_id}_input{ext}"
    output_path = OUTPUT_DIR / f"{job_id}_output.mp4"

    try:
        contents = await file.read()
        if len(contents) > MAX_SIZE_MB * 1024 * 1024:
            return JSONResponse({"error": f"File exceeds {MAX_SIZE_MB}MB limit"}, status_code=413)

        input_path.write_bytes(contents)
    except Exception as e:
        return JSONResponse({"error": f"Failed to save upload: {e}"}, status_code=500)

    # Run bypass
    options = {
        "crf": crf, "preset": preset, "fps": fps,
        "width": width, "height": height,
        "maxrate": maxrate, "bufsize": bufsize,
        "audio_bitrate": audio_bitrate,
        "device": device, "ios": ios,
        "inflate_loops": inflate_loops,
        "no_sharpen": no_sharpen, "no_grain": no_grain,
        "no_faststart": no_faststart, "no_spoof": no_spoof,
        "no_inflate": no_inflate,
    }

    success, log = run_bypass(input_path, output_path)

    if not success:
        # Clean up on failure
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        return JSONResponse({
            "error": "Processing failed",
            "log": log[-2000:],
        }, status_code=500)

    size_mb = output_path.stat().st_size / (1024 * 1024)

    return JSONResponse({
        "job_id": job_id,
        "filename": f"{Path(file.filename).stem}_tikbypass.mp4",
        "size_mb": round(size_mb, 1),
        "log": log[-2000:],
    })


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    output_path = OUTPUT_DIR / f"{job_id}_output.mp4"
    if not output_path.exists():
        return JSONResponse({"error": "File not found or expired"}, status_code=404)

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"tikbypass_{job_id}.mp4",
    )


@app.get("/api/health")
async def health():
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ffprobe_ok = shutil.which("ffprobe") is not None
    script_ok = TIKBYPASS_SCRIPT.exists()
    return {
        "status": "ok" if (ffmpeg_ok and ffprobe_ok and script_ok) else "degraded",
        "ffmpeg": ffmpeg_ok,
        "ffprobe": ffprobe_ok,
        "tikbypass_script": script_ok,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
