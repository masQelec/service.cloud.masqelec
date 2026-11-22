#!/usr/bin/env python3
"""Write only G3-AN's private synthetic M3U; NEVER touch G3-AB or G3-AM."""
import argparse
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
PRIVATE = RUNTIME / "g3an"
MARKER = RUNTIME / ".g3ab-synthetic-only"
EXPECTED_MARKER = "masqelec-g3ab-synthetic-v1\n"

def guard():
    if not MARKER.is_file() or MARKER.is_symlink() or MARKER.read_text() != EXPECTED_MARKER:
        raise RuntimeError("SYNTHETIC_MARKER_INVALID")
    if RUNTIME.is_symlink() or PRIVATE.is_symlink():
        raise RuntimeError("SYMLINK_DENIED")
    PRIVATE.mkdir(exist_ok=True)
    for name in ("playlist", "tvh_config"):
        d = PRIVATE / name
        if d.is_symlink() or (d.exists() and not d.is_dir()):
            raise RuntimeError("INVALID_G3AN_DIRECTORY")
        d.mkdir(exist_ok=True)
        if d.stat().st_uid != os.getuid():
            raise RuntimeError("G3AN_DIRECTORY_WRONG_OWNER")
    target = PRIVATE / "playlist" / "playlist.m3u"
    if target.is_symlink() or (target.exists() and target.stat().st_uid != os.getuid()):
        raise RuntimeError("G3AN_PLAYLIST_OWNER_OR_SYMLINK")
    return target

def playlist(stage):
    alpha_url = "http://streams/ch1.ts"
    if stage == "url":
        alpha_url = "http://streams/ch1.ts?g3an_url_test=1"
    return (
        "#EXTM3U\n"
        '#EXTINF:-1 CUID="g3an-001" tvg-chno="1" tvh-chnum="1" tvg-name="G3AN Alpha" group-title="G3AN SYNTHETIC",G3AN Alpha\n'
        + alpha_url + "\n"
        + '#EXTINF:-1 CUID="g3an-002" tvg-chno="2" tvh-chnum="2" tvg-name="G3AN Beta" group-title="G3AN SYNTHETIC",G3AN Beta\n'
        + "http://streams/ch2.ts\n"
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("init", "baseline", "url"))
    args = parser.parse_args()
    target = guard()
    if args.stage == "init" and target.exists():
        raise RuntimeError("G3AN_PLAYLIST_ALREADY_EXISTS")
    stage = "baseline" if args.stage == "init" else args.stage
    fd, temp = tempfile.mkstemp(prefix=".g3an-", dir=target.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(playlist(stage))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print("G3AN_PLAYLIST_STAGE=" + stage.upper())
    print("G3AN_PLAYLIST_PRIVATE_ONLY=YES")
    print("G3AN_PLAYLIST_URL=http://g3an-playlist/playlist.m3u")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print("G3AN_PREPARE=BLOCKED_" + str(exc))
        raise SystemExit(2)
