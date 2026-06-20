# 🧬 TikBypass

**Defy TikTok compression.** A multi-strategy video preprocessing engine that preserves quality through TikTok's re-encode pipeline.

```
Input → [Encode] → [Sharpen] → [Grain] → [Metadata Spoof] → [Faststart] → [5× Inflation] → Output
```

## How It Works

TikTok re-encodes every upload. Quality dies in the process — especially on Android and web uploads. TikBypass fights back with five stacked strategies:

| Strategy | What it does | Why |
|---|---|---|
| **Quality Encode** | H.264 High@L4.0, CRF 18, VBR 8Mbps | Start with headroom — compression has somewhere to fall |
| **Pre-sharpen** | Unsharp mask (luma, radius 5) | Edges survive re-compression; TikTok's smoother can't blur what's already crisp |
| **Grain Injection** | Subtle noise (strength 8, temporal+uniform) | Encoder sees "texture" and allocates bits instead of smearing |
| **Device Spoof** | iPhone 14 Pro metadata in `udta` atom | TikTok's device-tiered pipeline — iPhone Pro gets lighter compression |
| **Faststart** | `moov` atom before `mdat` | Proper streaming structure; avoids TikTok re-processing the container |
| **Table Inflation** | 5× sample-table inflation across all tracks | Hardens container structure against tampering detection |

## Quick Start

### CLI

```bash
python tikbypass.py input.mp4 -o output.mp4
```

That's it. All strategies enabled by default. Results in `output.mp4`.

```bash
# Max quality
python tikbypass.py input.mp4 -o output.mp4 --crf 16 --preset slow

# Light touch (no effects, metadata only)
python tikbypass.py input.mp4 -o output.mp4 --no-grain --no-sharpen --no-inflate

# Custom device
python tikbypass.py input.mp4 -o output.mp4 --device "iPhone16,2" --ios "17.0"
```

### Web App (Docker)

```bash
# Clone or copy to your VPS
cd tikbypass-web
docker compose up -d --build

# → http://your-server-ip
```

Drag-and-drop upload. Tweak options. Download processed video. No CLI needed.

**Requirements:** Docker + Docker Compose. Nothing else.

## CLI Reference

```
python tikbypass.py input.mp4 -o output.mp4 [options]
```

### Encoding
| Flag | Default | Description |
|---|---|---|
| `--crf` | 18 | H.264 quality (lower = better, 17-20 recommended) |
| `--preset` | medium | ffmpeg speed/quality tradeoff |
| `--fps` | 30 | Output framerate |
| `--width` | 1080 | Output width |
| `--height` | 1920 | Output height |
| `--maxrate` | 8M | Max video bitrate |
| `--bufsize` | 16M | VBV buffer size |
| `--audio-bitrate` | 192k | Audio bitrate |

### Bypass Strategies (all ON by default)
| Flag | Effect |
|---|---|
| `--no-sharpen` | Disable pre-sharpening |
| `--no-grain` | Disable grain injection |
| `--no-faststart` | Disable faststart |
| `--no-spoof` | Disable device metadata |
| `--no-inflate` | Disable table inflation |
| `--inflate-loops` | Inflation multiplier (default: 5) |

### Device Spoofing
| Flag | Default | Description |
|---|---|---|
| `--device` | iPhone15,2 | Apple device model ID |
| `--ios` | 16.4 | iOS version string |

### Supported Device IDs
- `iPhone15,2` — iPhone 14 Pro ⭐ default
- `iPhone15,3` — iPhone 14 Pro Max
- `iPhone16,1` — iPhone 15 Pro
- `iPhone16,2` — iPhone 15 Pro Max
- `iPhone14,3` — iPhone 13 Pro Max

## Web App

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Upload UI |
| `POST` | `/api/upload` | Upload + process video |
| `GET` | `/api/download/{job_id}` | Download processed file |
| `GET` | `/api/health` | Health check (ffmpeg + script status) |

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_DIR` | `/tmp/tikbypass/uploads` | Temp upload storage |
| `OUTPUT_DIR` | `/tmp/tikbypass/outputs` | Processed file storage |
| `MAX_UPLOAD_MB` | `500` | Max upload size |
| `KEEP_FILES_MIN` | `30` | Auto-cleanup age (minutes) |
| `TIKBYPASS_SCRIPT` | `/app/tikbypass.py` | Path to bypass engine |

### Production with HTTPS

1. Add your SSL certs to `nginx/`
2. Edit `nginx/default.conf` — add the `server { listen 443 ssl; }` block
3. Or put Cloudflare in front, set SSL to Full, and call it done

## Architecture

```
tikbypass.py              ← CLI engine (pure Python + ffmpeg)

tikbypass-web/
├── Dockerfile            ← Multi-stage: debian(ffmpeg) → python:3.12
├── docker-compose.yml    ← app + nginx, tmpfs for /tmp
├── nginx/default.conf    ← Reverse proxy, 500MB upload, streaming
└── app/
    ├── main.py           ← FastAPI — /api/upload, /api/download
    ├── templates/index.html
    └── static/
        ├── css/style.css
        └── js/app.js
```

## Dependencies

- **Python 3.9+**
- **ffmpeg** + **ffprobe** (CLI and web)

Web app extras (auto-installed in Docker):
- FastAPI, Uvicorn, Jinja2, python-multipart

## Notes

- TikTok's compression pipeline is a moving target. YMMV.
- Grain injection is subtle (strength 8). It shouldn't be visible — if you can see it, the strength is wrong.
- Sample-table inflation increases file size slightly. The 5× default is a good balance.
- Processing time: ~1-3 minutes for a 1-minute 1080p video on modest hardware.
