#!/usr/bin/env python3
"""Prepare an independent synthetic HTTP M3U for G3-AM.

Never changes G3-AB original runtime/playlist or runtime/tvh_config.
"""
from pathlib import Path
import argparse
import os
import tempfile

BASE = Path(__file__).resolve().parent.parent
RUNTIME = BASE / "runtime"
PRIVATE = RUNTIME / "g3am"
MARKER = RUNTIME / ".g3ab-synthetic-only"
EXPECTED = "masqelec-g3ab-synthetic-v1\n"


def guard():
    if not MARKER.is_file() or MARKER.is_symlink() or MARKER.read_text() != EXPECTED:
        raise RuntimeError("G3AM_SYNTHETIC_MARKER_INVALID")
    if PRIVATE.is_symlink() or (PRIVATE.exists() and not PRIVATE.is_dir()):
        raise RuntimeError("G3AM_PRIVATE_ROOT_INVALID")
    PRIVATE.mkdir(exist_ok=True)
    for name in ("playlist", "tvh_config"):
        child = PRIVATE / name
        if child.is_symlink() or (child.exists() and not child.is_dir()):
            raise RuntimeError("G3AM_PRIVATE_DIRECTORY_INVALID")
        child.mkdir(exist_ok=True)
    if (PRIVATE / "tvh_config").stat().st_uid != os.getuid():
        raise RuntimeError("G3AM_TVH_CONFIG_OWNER_UNEXPECTED")


def playlist(stage):
    alpha = "G3AM Alpha Renamed" if stage == "rename" else "G3AM Alpha"
    return (
        '#EXTM3U\n'
        f'#EXTINF:-1 CUID="g3am-001" tvg-chno="1" tvh-chnum="1" tvg-name="{alpha}" group-title="G3AM SYNTHETIC",{alpha}\n'
        'http://streams/ch1.ts\n'
        '#EXTINF:-1 CUID="g3am-002" tvg-chno="2" tvh-chnum="2" tvg-name="G3AM Beta" group-title="G3AM SYNTHETIC",G3AM Beta\n'
        'http://streams/ch2.ts\n'
    )


def run(stage):
    guard()
    target = PRIVATE / "playlist" / "playlist.m3u"
    if target.is_symlink():
        raise RuntimeError("G3AM_PLAYLIST_SYMLINK_DENIED")
    if stage == "init" and target.exists():
        raise RuntimeError("G3AM_PLAYLIST_ALREADY_EXISTS")
    content = playlist("baseline" if stage == "init" else stage)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".g3am-")
    try:
        # mkstemp defaults to 0600. The nginx worker in the separate
        # playlist container must be able to read this synthetic, public M3U.
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(f"G3AM_STAGE={stage.upper()}")
    print("G3AM_PLAYLIST_TARGET=PRIVATE_ONLY")
    print("G3AM_ORIGINAL_PLAYLIST_UNTOUCHED=YES")
    print("G3AM_HTTP_SOURCE=http://g3am-playlist/playlist.m3u")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("init", "baseline", "rename"))
    args = parser.parse_args()
    try:
        run(args.stage)
    except (OSError, RuntimeError) as exc:
        print("G3AM_PREPARE=BLOCKED")
        print("REASON=" + str(exc))
        raise SystemExit(2)
