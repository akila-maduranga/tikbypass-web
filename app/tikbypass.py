#!/usr/bin/env python3
"""
TikBypass — TikTok Compression Bypass Engine
=============================================
Multi-strategy video preprocessing to preserve quality through TikTok's re-encode pipeline.

Strategies applied (in order):
  1. High-quality re-encode    — ffmpeg with optimal params
  2. Pre-sharpening            — unsharp mask so detail survives compression
  3. Subtle grain injection    — tricks rate-control into preserving texture
  4. Device metadata spoofing  — iPhone 14 Pro Max fingerprint (TikTok's preferential tier)
  5. Faststart                 — moov atom repositioning for ingestion compatibility
  6. Sample-table hardening    — optional stbl inflation (advanced)

Usage:
  python tikbypass.py input.mp4 -o output.mp4
  python tikbypass.py input.mp4 -o output.mp4 --no-grain --no-sharpen
  python tikbypass.py input.mp4 -o output.mp4 --device "iPhone15,2" --ios "16.4"
"""

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Config:
    input_path: Path
    output_path: Path
    sharpen: bool = True
    grain: bool = True
    faststart: bool = True
    spoof_device: bool = True
    inflate_stbl: bool = False          # aggressive — off by default
    inflate_loops: int = 3
    device_model: str = "iPhone15,2"    # iPhone 14 Pro
    ios_version: str = "16.4"
    crf: int = 18                       # lower = better quality (17-20 sweet spot)
    preset: str = "medium"              # ffmpeg preset
    fps: int = 30
    width: int = 1080
    height: int = 1920
    maxrate: str = "8M"
    bufsize: str = "16M"
    audio_bitrate: str = "192k"
    verbose: bool = False

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"  {msg}", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════
# FFMPEG ENCODING ENGINE
# ═══════════════════════════════════════════════════════════════════

def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def build_vf_chain(cfg: Config) -> str:
    """Construct the ffmpeg filtergraph."""
    filters = []

    # Scale to target resolution, keep aspect ratio with padding
    filters.append(
        f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
        f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2"
    )

    # FPS normalization
    filters.append(f"fps={cfg.fps}")

    # Pre-sharpen: unsharp mask — makes edges survive compression
    if cfg.sharpen:
        # luma sharpen (amount=1.2, radius=1.0, threshold=0.05)
        filters.append("unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.2")

    # Subtle grain — tricks rate-control into allocating more bits to textured areas
    if cfg.grain:
        # noise strength kept low (8-10) so it's imperceptible but effective
        filters.append("noise=alls=8:allf=t+u")

    # Ensure yuv420p (required for broad compatibility)
    filters.append("format=yuv420p")

    return ",".join(filters)


def encode_video(cfg: Config, tmp_path: Path) -> bool:
    """Re-encode with TikTok-optimal parameters. Outputs to temp file."""
    vf = build_vf_chain(cfg)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(cfg.input_path),
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level", "4.0",
        "-preset", cfg.preset,
        "-crf", str(cfg.crf),
        "-maxrate", cfg.maxrate,
        "-bufsize", cfg.bufsize,
        "-bf", "2",                    # B-frames
        "-refs", "3",                  # reference frames
        "-g", str(cfg.fps * 2),        # GOP size = 2 seconds
        "-keyint_min", str(cfg.fps),
        "-sc_threshold", "0",          # disable scene-cut detection for consistent GOP
        "-x264-params", "no-deblock=1:no-fast-pskip=1",  # preserve fine detail
        "-vf", vf,
        "-c:a", "aac",
        "-b:a", cfg.audio_bitrate,
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "empty_moov",     # we handle moov ourselves
        str(tmp_path),
    ]

    cfg.log("[ENCODE] Running ffmpeg...")
    cfg.log(f"[ENCODE] CRF={cfg.crf}, preset={cfg.preset}, sharpen={cfg.sharpen}, grain={cfg.grain}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"[ERROR] ffmpeg failed:\n{result.stderr[-600:]}", file=sys.stderr)
        return False

    cfg.log("[ENCODE] Done.")
    return True


# ═══════════════════════════════════════════════════════════════════
# MP4 BOX MANIPULATION (pure Python, zero deps)
# ═══════════════════════════════════════════════════════════════════

class Box:
    """ISOBMFF box — recursive container."""
    __slots__ = ("box_type", "data", "children")

    def __init__(self, box_type: bytes, data: bytes = b"",
                 children: Optional[list["Box"]] = None):
        self.box_type = box_type
        self.data = data
        self.children = children if children is not None else []

    @property
    def size(self) -> int:
        s = 8  # header
        if self.children:
            s += sum(c.size for c in self.children)
        else:
            s += len(self.data)
        return s

    def build(self) -> bytes:
        s = self.size
        if s > 0xFFFFFFFF:
            header = struct.pack(">I", 1) + self.box_type + struct.pack(">Q", s)
        else:
            header = struct.pack(">I", s) + self.box_type

        if self.children:
            return header + b"".join(c.build() for c in self.children)
        return header + self.data

    def find(self, box_type: bytes):
        for c in self.children:
            if c.box_type == box_type:
                return c
        return None

    def find_all(self, box_type: bytes):
        return [c for c in self.children if c.box_type == box_type]


CONTAINER_TYPES = {b"moov", b"trak", b"mdia", b"minf", b"stbl",
                   b"edts", b"udta", b"dinf", b"mvex", b"mfra",
                   b"moof", b"tref", b"meta", b"ilst", b"iprp"}


def parse_boxes(data: bytes, start: int = 0, end: Optional[int] = None) -> list[Box]:
    """Parse ISOBMFF box hierarchy from raw bytes."""
    if end is None:
        end = len(data)
    boxes = []
    pos = start

    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        hdr_sz = 8

        if size == 1:  # 64-bit extended size
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr_sz = 16
        elif size == 0:  # runs to end
            size = end - pos

        if size < hdr_sz or pos + size > end:
            break

        btype = data[pos + 4:pos + 8]
        payload = data[pos + hdr_sz:pos + size]

        if btype in CONTAINER_TYPES:
            boxes.append(Box(btype, b"", parse_boxes(payload)))
        else:
            boxes.append(Box(btype, payload))

        pos += size

    return boxes


def find_box(data: bytes, box_type: bytes,
             start: int = 0, end: Optional[int] = None):
    """Find a top-level box by type. Returns (offset, size) or (-1, 0)."""
    if end is None:
        end = len(data)
    pos = start

    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        hdr_sz = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr_sz = 16
        elif size == 0:
            size = end - pos

        if size < hdr_sz or pos + size > end:
            break

        if data[pos + 4:pos + 8] == box_type:
            return pos, size

        pos += size

    return -1, 0


# ── stco/co64 offset adjustment ──────────────────────────────────

def adjust_offsets(data: bytearray, delta: int, start: int, end: int):
    """Recursively walk boxes and fix chunk offsets by delta."""
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        hdr_sz = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr_sz = 16
        elif size == 0:
            size = end - pos
        if size < hdr_sz or pos + size > end:
            break

        btype = data[pos + 4:pos + 8]

        if btype in CONTAINER_TYPES:
            adjust_offsets(data, delta, pos + hdr_sz, pos + size)
        elif btype == b"stco":
            count = struct.unpack(">I", data[pos + 8:pos + 12])[0]
            entry_start = pos + 12
            for i in range(count):
                idx = entry_start + i * 4
                if idx + 4 > pos + size:
                    break
                off = struct.unpack(">I", data[idx:idx + 4])[0]
                data[idx:idx + 4] = struct.pack(">I", (off + delta) & 0xFFFFFFFF)
        elif btype == b"co64":
            count = struct.unpack(">I", data[pos + 8:pos + 12])[0]
            entry_start = pos + 12
            for i in range(count):
                idx = entry_start + i * 8
                if idx + 8 > pos + size:
                    break
                off = struct.unpack(">Q", data[idx:idx + 8])[0]
                data[idx:idx + 8] = struct.pack(">Q", off + delta)

        pos += size


# ── Faststart: move moov before mdat ─────────────────────────────

def apply_faststart(data: bytes, cfg: Config) -> bytes:
    """Move moov atom to the front (after ftyp). TikTok requires this."""
    ftyp_off, ftyp_sz = find_box(data, b"ftyp")
    moov_off, moov_sz = find_box(data, b"moov")
    mdat_off, mdat_sz = find_box(data, b"mdat")

    if -1 in (ftyp_off, moov_off, mdat_sz):
        cfg.log("[FASTSTART] Missing expected top-level boxes, skipping.")
        return data

    if moov_off < mdat_off:
        cfg.log("[FASTSTART] moov already at front, skipping.")
        return data

    cfg.log("[FASTSTART] Moving moov atom before mdat...")

    ftyp = data[ftyp_off:ftyp_off + ftyp_sz]
    moov = data[moov_off:moov_off + moov_sz]
    mdat = data[mdat_off:mdat_off + mdat_sz]

    # Collect everything else
    rest = b""
    pos = ftyp_sz
    while pos < len(data):
        sz = struct.unpack(">I", data[pos:pos + 4])[0]
        hdr_sz = 8
        if sz == 1:
            sz = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr_sz = 16
        elif sz == 0:
            break
        if sz < hdr_sz:
            break
        if pos == moov_off or pos == mdat_off:
            pos += sz
            continue
        rest += data[pos:pos + sz]
        pos += sz

    new = bytearray()
    new.extend(ftyp)
    new.extend(moov)
    new.extend(rest)
    new.extend(mdat)

    # Fix stco/co64 offsets
    new_mdat_off = ftyp_sz + moov_sz + len(rest)
    delta = new_mdat_off - mdat_off
    adjust_offsets(new, delta, ftyp_sz, ftyp_sz + moov_sz)

    return bytes(new)


# ── Metadata injection ───────────────────────────────────────────

def inject_ios_metadata(moov: Box, cfg: Config) -> Box:
    """Inject or replace udta with iPhone device metadata."""
    cfg.log(f"[META] Injecting device fingerprint: {cfg.device_model} / iOS {cfg.ios_version}")

    # Remove existing udta
    moov.children = [c for c in moov.children if c.box_type != b"udta"]

    udta = Box(b"udta", b"", [
        Box(b"\xa9too", f"{cfg.ios_version}\x00".encode()),
        Box(b"\xa9mak", b"Apple\x00"),
        Box(b"\xa9mod", f"{cfg.device_model}\x00".encode()),
        Box(b"\xa9swr", f"{cfg.ios_version}\x00".encode()),
        # Additional metadata TikTok may inspect
        Box(b"\xa9day", b"2024\x00"),
    ])
    moov.children.append(udta)
    return moov


# ── Sample-table inflation (optional aggressive strategy) ────────

def _inflate_table(data: bytes, loop_count: int,
                   key_adjust: bool = False,
                   orig_value: int = 0) -> bytes:
    """Generic table inflator: repeat entries loop_count times."""
    ver_flags = data[:4]
    entry_count = struct.unpack(">I", data[4:8])[0]
    entries = data[8:]

    new_entries = []
    for i in range(loop_count):
        if key_adjust and orig_value > 0:
            # Adjust key sample numbers (stss)
            for j in range(entry_count):
                off = j * 4
                sn = struct.unpack(">I", entries[off:off + 4])[0]
                new_entries.append(struct.pack(">I", sn + i * orig_value))
        else:
            new_entries.append(entries)

    new_count = entry_count * loop_count
    return ver_flags + struct.pack(">I", new_count) + b"".join(new_entries)


def _inflate_stsc(data: bytes, loop_count: int, orig_chunks: int) -> bytes:
    """stsc inflator — adjusts first_chunk offsets per loop."""
    ver_flags = data[:4]
    entry_count = struct.unpack(">I", data[4:8])[0]
    entries = data[8:]

    new_entries = b""
    for i in range(loop_count):
        for j in range(entry_count):
            off = j * 12
            fc = struct.unpack(">I", entries[off:off + 4])[0]
            spc = struct.unpack(">I", entries[off + 4:off + 8])[0]
            sdi = struct.unpack(">I", entries[off + 8:off + 12])[0]
            new_entries += struct.pack(">III", fc + i * orig_chunks, spc, sdi)

    new_count = entry_count * loop_count
    return ver_flags + struct.pack(">I", new_count) + new_entries


def _inflate_duration(data: bytes, loop_count: int) -> bytes:
    """Inflate duration fields in mvhd/tkhd/mdhd."""
    ver = data[0]
    if ver == 0:
        dur = struct.unpack(">I", data[16:20])[0]
        return data[:16] + struct.pack(">I", dur * loop_count) + data[20:]
    else:
        dur = struct.unpack(">Q", data[24:32])[0]
        return data[:24] + struct.pack(">Q", dur * loop_count) + data[32:]


def _inflate_tkhd(data: bytes, loop_count: int) -> bytes:
    ver = data[0]
    if ver == 0:
        dur = struct.unpack(">I", data[20:24])[0]
        return data[:20] + struct.pack(">I", dur * loop_count) + data[24:]
    else:
        dur = struct.unpack(">Q", data[28:36])[0]
        return data[:28] + struct.pack(">Q", dur * loop_count) + data[36:]


def _inflate_elst(data: bytes, loop_count: int) -> bytes:
    ver = data[0]
    flags = data[1:4]
    entry_count = struct.unpack(">I", data[4:8])[0]
    entry_sz = 12 if ver == 0 else 20

    new_entries = b""
    for i in range(entry_count):
        entry = data[8 + i * entry_sz:8 + (i + 1) * entry_sz]
        if ver == 0:
            dur = struct.unpack(">I", entry[:4])[0]
            new_entries += struct.pack(">I", dur * loop_count) + entry[4:]
        else:
            dur = struct.unpack(">Q", entry[:8])[0]
            new_entries += struct.pack(">Q", dur * loop_count) + entry[8:]

    return struct.pack(">B", ver) + flags + struct.pack(">I", entry_count) + new_entries


def inflate_stbl(stbl: Box, loop_count: int) -> Box:
    """Inflate all sample tables in stbl for one track."""
    # Calculate original totals
    orig_chunks = 0
    orig_samples = 0
    for c in stbl.children:
        if c.box_type in (b"stco", b"co64"):
            orig_chunks = struct.unpack(">I", c.data[4:8])[0]
        elif c.box_type == b"stts":
            count = struct.unpack(">I", c.data[4:8])[0]
            entries = c.data[8:]
            orig_samples = sum(struct.unpack(">I", entries[i * 8:i * 8 + 4])[0]
                              for i in range(count))

    new_children = []
    for c in stbl.children:
        bt = c.box_type
        if bt in (b"stts", b"stsz", b"stco", b"co64", b"ctts"):
            new_children.append(Box(bt, _inflate_table(c.data, loop_count)))
        elif bt == b"stsc":
            new_children.append(Box(bt, _inflate_stsc(c.data, loop_count, orig_chunks)))
        elif bt == b"stss":
            new_children.append(Box(bt, _inflate_table(c.data, loop_count, True, orig_samples)))
        else:
            new_children.append(c)

    return Box(b"stbl", b"", new_children)


def inflate_trak(trak: Box, loop_count: int) -> Box:
    new_children = []
    for c in trak.children:
        if c.box_type == b"tkhd":
            new_children.append(Box(b"tkhd", _inflate_tkhd(c.data, loop_count)))
        elif c.box_type == b"mdia":
            new_mdia = []
            for mc in c.children:
                if mc.box_type == b"mdhd":
                    new_mdia.append(Box(b"mdhd", _inflate_duration(mc.data, loop_count)))
                elif mc.box_type == b"minf":
                    new_minf = []
                    for mfc in mc.children:
                        if mfc.box_type == b"stbl":
                            new_minf.append(inflate_stbl(mfc, loop_count))
                        else:
                            new_minf.append(mfc)
                    new_mdia.append(Box(b"minf", b"", new_minf))
                else:
                    new_mdia.append(mc)
            new_children.append(Box(b"mdia", b"", new_mdia))
        elif c.box_type == b"edts":
            new_edts = []
            for ec in c.children:
                if ec.box_type == b"elst":
                    new_edts.append(Box(b"elst", _inflate_elst(ec.data, loop_count)))
                else:
                    new_edts.append(ec)
            new_children.append(Box(b"edts", b"", new_edts))
        else:
            new_children.append(c)
    return Box(b"trak", b"", new_children)


def inflate_moov(moov: Box, cfg: Config) -> Box:
    """Inflate all duration and sample tables in moov."""
    loop = cfg.inflate_loops
    new_children = []
    for c in moov.children:
        if c.box_type == b"mvhd":
            new_children.append(Box(b"mvhd", _inflate_duration(c.data, loop)))
        elif c.box_type == b"trak":
            new_children.append(inflate_trak(c, loop))
        elif c.box_type == b"udta":
            continue  # replaced later
        else:
            new_children.append(c)
    return Box(b"moov", b"", new_children)


def apply_stbl_inflation(data: bytes, cfg: Config) -> bytes:
    """Top-level: parse moov, inflate, rebuild."""
    cfg.log(f"[INFLATE] Inflating sample tables {cfg.inflate_loops}x...")

    moov_off, moov_sz = find_box(data, b"moov")
    if moov_off == -1:
        cfg.log("[INFLATE] No moov found, skipping.")
        return data

    moov_data = data[moov_off:moov_off + moov_sz]
    old_moov = parse_boxes(moov_data)[0]
    new_moov = inflate_moov(old_moov, cfg)
    new_moov_data = new_moov.build()

    result = bytearray()
    result.extend(data[:moov_off])
    result.extend(new_moov_data)
    result.extend(data[moov_off + moov_sz:])

    delta = len(new_moov_data) - moov_sz
    if delta != 0:
        adjust_offsets(result, delta, moov_off + 8, moov_off + len(new_moov_data))

    return bytes(result)


# ── Full metadata pass ───────────────────────────────────────────

def apply_metadata(data: bytes, cfg: Config) -> bytes:
    """Parse moov, inject device metadata, rebuild."""
    cfg.log("[META] Applying device metadata...")

    moov_off, moov_sz = find_box(data, b"moov")
    if moov_off == -1:
        cfg.log("[META] No moov found, skipping.")
        return data

    moov_data = data[moov_off:moov_off + moov_sz]
    old_moov = parse_boxes(moov_data)[0]
    new_moov = inject_ios_metadata(old_moov, cfg)
    new_moov_data = new_moov.build()

    result = bytearray()
    result.extend(data[:moov_off])
    result.extend(new_moov_data)
    result.extend(data[moov_off + moov_sz:])

    delta = len(new_moov_data) - moov_sz
    if delta != 0:
        adjust_offsets(result, delta, moov_off + 8, moov_off + len(new_moov_data))

    return bytes(result)


# ═══════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════

def process(cfg: Config) -> bool:
    """Run the full bypass pipeline."""
    if not cfg.input_path.exists():
        print(f"[ERROR] Input not found: {cfg.input_path}", file=sys.stderr)
        return False

    if not check_ffmpeg():
        print("[ERROR] ffmpeg not found in PATH.", file=sys.stderr)
        return False

    tmp = cfg.output_path.with_suffix(".tikbypass.tmp.mp4")

    # ── Stage 1: Encode ──
    print("[1/4] Encoding with quality-preserving parameters...")
    if not encode_video(cfg, tmp):
        tmp.unlink(missing_ok=True)
        return False

    # ── Stage 2: Post-processing ──
    with open(tmp, "rb") as f:
        data = f.read()

    print("[2/4] Post-processing MP4 structure...")

    # Optional: sample-table inflation (aggressive)
    if cfg.inflate_stbl:
        data = apply_stbl_inflation(data, cfg)

    # Device metadata injection
    if cfg.spoof_device:
        data = apply_metadata(data, cfg)
        print(f"  ✓ Device spoofed → {cfg.device_model} / iOS {cfg.ios_version}")

    # Faststart
    if cfg.faststart:
        data = apply_faststart(data, cfg)
        print("  ✓ Faststart applied (moov → front)")

    # Write final
    cfg.output_path.write_bytes(data)
    tmp.unlink(missing_ok=True)

    # ── Stage 3: Report ──
    size_mb = cfg.output_path.stat().st_size / (1024 * 1024)
    print(f"[3/4] Output: {cfg.output_path} ({size_mb:.1f} MB)")

    # ── Stage 4: Quick validation ──
    print("[4/4] Validating output...")
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(cfg.output_path)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        print("  ✓ Output is valid MP4")
    else:
        print("  ⚠ ffprobe validation failed (file may still be valid)")

    print("\n✅ Done. Upload-ready.")
    return True


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="TikBypass — TikTok compression bypass engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.mp4 -o output.mp4
  %(prog)s input.mp4 -o output.mp4 --crf 16 --device "iPhone15,3"
  %(prog)s input.mp4 -o output.mp4 --inflate --inflate-loops 5
  %(prog)s input.mp4 -o output.mp4 --no-grain --no-sharpen
        """,
    )

    parser.add_argument("input", type=Path, help="Input video file")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="Output video file")

    # Encoding
    enc = parser.add_argument_group("Encoding")
    enc.add_argument("--crf", type=int, default=18,
                     help="H.264 CRF quality (lower=better, 17-20 recommended) [default: 18]")
    enc.add_argument("--preset", default="medium",
                     choices=["ultrafast", "veryfast", "faster", "fast",
                              "medium", "slow", "slower", "veryslow"],
                     help="ffmpeg preset [default: medium]")
    enc.add_argument("--fps", type=int, default=30, help="Output FPS [default: 30]")
    enc.add_argument("--width", type=int, default=1080, help="Output width [default: 1080]")
    enc.add_argument("--height", type=int, default=1920, help="Output height [default: 1920]")
    enc.add_argument("--maxrate", default="8M", help="Max video bitrate [default: 8M]")
    enc.add_argument("--bufsize", default="16M", help="VBV buffer size [default: 16M]")
    enc.add_argument("--audio-bitrate", default="192k", help="Audio bitrate [default: 192k]")

    # Strategies
    strat = parser.add_argument_group("Bypass Strategies")
    strat.add_argument("--no-sharpen", action="store_true",
                       help="Disable pre-sharpening")
    strat.add_argument("--no-grain", action="store_true",
                       help="Disable grain injection")
    strat.add_argument("--no-faststart", action="store_true",
                       help="Disable faststart (moov repositioning)")
    strat.add_argument("--no-spoof", action="store_true",
                       help="Disable device metadata spoofing")
    strat.add_argument("--inflate", action="store_true",
                       help="Enable aggressive sample-table inflation (off by default)")
    strat.add_argument("--inflate-loops", type=int, default=3,
                       help="Inflation loop count [default: 3]")

    # Device
    dev = parser.add_argument_group("Device Spoofing")
    dev.add_argument("--device", default="iPhone15,2",
                     help="Device model ID [default: iPhone15,2 (iPhone 14 Pro)]")
    dev.add_argument("--ios", default="16.4",
                     help="iOS version string [default: 16.4]")

    # Misc
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    cfg = Config(
        input_path=args.input.resolve(),
        output_path=args.output.resolve(),
        sharpen=not args.no_sharpen,
        grain=not args.no_grain,
        faststart=not args.no_faststart,
        spoof_device=not args.no_spoof,
        inflate_stbl=args.inflate,
        inflate_loops=args.inflate_loops,
        device_model=args.device,
        ios_version=args.ios,
        crf=args.crf,
        preset=args.preset,
        fps=args.fps,
        width=args.width,
        height=args.height,
        maxrate=args.maxrate,
        bufsize=args.bufsize,
        audio_bitrate=args.audio_bitrate,
        verbose=args.verbose,
    )

    print(f"TikBypass 🧬 — {cfg.input_path.name} → {cfg.output_path.name}")
    print(f"  Strategies: sharpen={cfg.sharpen} grain={cfg.grain} "
          f"faststart={cfg.faststart} spoof={cfg.spoof_device} inflate={cfg.inflate_stbl}")
    if cfg.spoof_device:
        print(f"  Device: {cfg.device_model} / iOS {cfg.ios_version}")
    print()

    success = process(cfg)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
