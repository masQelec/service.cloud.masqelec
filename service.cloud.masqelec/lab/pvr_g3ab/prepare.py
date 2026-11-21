#!/usr/bin/env python3
"""G3-AB independent synthetic CUID playlist stages.

Only writes lab/pvr_g3ab/runtime, never G3-W or CoreELEC.
Stage changes are intentionally one-dimensional and use stable CUIDs.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
GUARD = RUNTIME / ".g3ab-synthetic-only"
DIRS = ("playlist", "streams", "tvh_config", "recordings", "kodi_home")
CUIDS = ("g3ab-001", "g3ab-002")

# order must be explicit, to make changes measurable.
STAGES = ("baseline", "rename", "url", "group", "reorder", "homonym", "restored")


def entries(stage):
    if stage not in STAGES:
        raise ValueError("INVALID_STAGE")
    rows = [
        {"cuid": CUIDS[0], "name": "G3AB Alpha", "group": "G3AB ORIGINAL",
         "url": "http://streams/ch1.ts", "number": 1},
        {"cuid": CUIDS[1], "name": "G3AB Beta", "group": "G3AB ORIGINAL",
         "url": "http://streams/ch2.ts", "number": 2},
    ]
    if stage == "rename":
        rows[0]["name"] = "G3AB Alpha Renamed"
    elif stage == "url":
        rows[0]["url"] = "http://streams/ch1-alt.ts"
    elif stage == "group":
        rows[0]["group"] = "G3AB MOVED"
    elif stage == "reorder":
        rows.reverse()
    elif stage == "homonym":
        rows[1]["name"] = rows[0]["name"]
    return rows


def playlist(stage):
    lines = ["#EXTM3U"]
    for entry in entries(stage):
        lines.append(
            '#EXTINF:-1 CUID="{cuid}" tvg-chno="{number}" tvh-chnum="{number}" '
            'tvg-name="{name}" group-title="{group}",{name}'.format(**entry)
        )
        lines.append(entry["url"])
    return "\n".join(lines) + "\n"


def preflight():
    if ROOT.is_symlink() or RUNTIME.is_symlink():
        raise RuntimeError("SYMLINK_DIRECTORY_DENIED")
    if RUNTIME.exists() and not RUNTIME.is_dir():
        raise RuntimeError("INVALID_RUNTIME")
    RUNTIME.mkdir(exist_ok=True)
    for name in DIRS:
        path = RUNTIME / name
        if path.is_symlink():
            raise RuntimeError("SYMLINK_DIRECTORY_DENIED")
        path.mkdir(exist_ok=True)
    if GUARD.is_symlink():
        raise RuntimeError("MARKER_SYMLINK_DENIED")
    if GUARD.exists() and GUARD.read_text() != "masqelec-g3ab-synthetic-v1\n":
        raise RuntimeError("INVALID_LAB_MARKER")
    if not GUARD.exists():
        GUARD.write_text("masqelec-g3ab-synthetic-v1\n")


def make_streams():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFMPEG_NOT_INSTALLED")
    for i in (1, 2):
        dest = RUNTIME / "streams" / ("ch%d.ts" % i)
        if dest.is_symlink():
            raise RuntimeError("STREAM_SYMLINK_DENIED")
        if not dest.exists():
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
                "-f", "lavfi", "-i", "sine=frequency=%d:sample_rate=48000" % (350 + i * 130),
                "-t", "12", "-c:v", "mpeg2video", "-b:v", "500k",
                "-c:a", "mp2", "-b:a", "64k", "-mpegts_service_id", str(i),
                "-metadata", "service_name=G3AB Signal %d" % i,
                "-f", "mpegts", str(dest),
            ]
            subprocess.run(cmd, check=True, timeout=90,
                           stdout=subprocess.DEVNULL)
    alternate = RUNTIME / "streams" / "ch1-alt.ts"
    if alternate.is_symlink():
        raise RuntimeError("STREAM_SYMLINK_DENIED")
    if not alternate.exists():
        shutil.copyfile(RUNTIME / "streams" / "ch1.ts", alternate)


def atomic_write(path, content):
    if path.is_symlink():
        raise RuntimeError("PLAYLIST_SYMLINK_DENIED")
    fd, tmp = tempfile.mkstemp(prefix=".g3ab-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(stage):
    preflight()
    if stage == "baseline":
        make_streams()
    elif not all((RUNTIME / "streams" / name).is_file()
                 for name in ("ch1.ts", "ch2.ts", "ch1-alt.ts")):
        raise RuntimeError("LAB_STREAMS_NOT_PREPARED")
    atomic_write(RUNTIME / "playlist" / "playlist.m3u", playlist(stage))
    print("G3AB_STAGE=" + stage.upper())
    print("G3AB_CUID_COUNT=2")
    print("G3AB_MASTER_UNTOUCHED=YES")
    print("G3AB_G3W_UNTOUCHED=YES")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=STAGES)
    args = parser.parse_args()
    try:
        run(args.stage)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print("G3AB=BLOCKED")
        print("REASON=" + (str(exc) if type(exc) is RuntimeError else type(exc).__name__))
        sys.exit(2)
