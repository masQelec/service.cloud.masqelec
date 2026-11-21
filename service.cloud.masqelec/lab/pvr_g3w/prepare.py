#!/usr/bin/env python3
"""Build synthetic MPEGTS and switch between isolated 2/3-channel playlists.

The generated playlist is *only* inside lab/pvr_g3w/runtime/playlist.
No master M3U, network or Kodi DB is accessed or altered.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
SAFE_NAMES = ("tvh_config", "recordings", "playlist", "streams")
GUARD = RUNTIME / ".g3w-synthetic-lab"


def _preflight():
    if ROOT.is_symlink() or RUNTIME.is_symlink():
        raise RuntimeError("SYMLINK_DIRECTORY_DENIED")
    if RUNTIME.exists() and not RUNTIME.is_dir():
        raise RuntimeError("INVALID_RUNTIME")
    RUNTIME.mkdir(exist_ok=True)
    for name in SAFE_NAMES:
        folder = RUNTIME / name
        if folder.is_symlink():
            raise RuntimeError("SYMLINK_DIRECTORY_DENIED")
        folder.mkdir(exist_ok=True)
    if GUARD.is_symlink():
        raise RuntimeError("SYMLINK_MARKER_DENIED")
    if GUARD.exists() and GUARD.read_text() != "masqelec-g3w-synthetic-v1\n":
        raise RuntimeError("INVALID_LAB_MARKER")
    if not GUARD.exists():
        GUARD.write_text("masqelec-g3w-synthetic-v1\n")


def _playlist(stage):
    entries = []
    for number in range(1, 4 if stage == "added" else 3):
        entries.extend((
            '#EXTINF:-1 tvh-chnum="{0}" tvg-chno="{0}" '
            'group-title="G3W TEST",G3W Synthetic {0}'.format(number),
            "http://streams/ch{0}.ts".format(number)
        ))
    return "#EXTM3U\n" + "\n".join(entries) + "\n"


def _write_atomic(dest, content):
    if dest.is_symlink():
        raise RuntimeError("PLAYLIST_SYMLINK_DENIED")
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=".playlist-g3w-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def prepare_streams():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFMPEG_NOT_INSTALLED")
    for number in range(1, 4):
        target = RUNTIME / "streams" / ("ch%d.ts" % number)
        if target.is_symlink():
            raise RuntimeError("STREAM_SYMLINK_DENIED")
        if target.exists():
            continue
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=%d:sample_rate=48000" % (400 + number * 100),
            "-t", "12", "-c:v", "mpeg2video", "-b:v", "500k",
            "-c:a", "mp2", "-b:a", "64k", "-mpegts_service_id", str(number),
            "-metadata", "service_name=G3W Synthetic %d" % number,
            "-f", "mpegts", str(target)
        ]
        subprocess.run(command, check=True, timeout=90, stdout=subprocess.DEVNULL)
    return 3


def run(stage):
    if stage not in ("before", "added", "removed"):
        raise RuntimeError("INVALID_STAGE")
    _preflight()
    if stage == "before":
        prepare_streams()
    elif not all((RUNTIME / "streams" / ("ch%d.ts" % n)).is_file()
                 for n in range(1, 4)):
        raise RuntimeError("LAB_STREAMS_NOT_PREPARED")
    dest = RUNTIME / "playlist" / "playlist.m3u"
    _write_atomic(dest, _playlist(stage))
    print("G3W_STAGE=" + stage.upper())
    print("G3W_CHANNELS=" + str(3 if stage == "added" else 2))
    print("G3W_PLAYLIST_ONLY_IN_LAB=YES")
    print("G3W_MASTER_UNTOUCHED=YES")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("before", "added", "removed"))
    options = parser.parse_args()
    try:
        run(options.stage)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print("G3W=BLOCKED")
        print("REASON=" + (str(exc) if type(exc) is RuntimeError else type(exc).__name__))
        sys.exit(2)
