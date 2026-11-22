#!/usr/bin/env python3
"""G3-AO: opt-in surgical patch on already G3-AN-patched isolated source.

Only permits updating *configured* IPTV URL while stream currently active.
Tvheadend iptv_input_start_mux() snapshots URL into mm_iptv_url_raw;
no forced disconnect, mux deletion, or service replacement is introduced.
MUST validate stream behavior in synthetic lab before CoreELEC use.
"""
import argparse
from pathlib import Path
import sys

EXPECTED = Path("/home/ubuntu/tvheadend-g3an-upstream")
OLD_PREFLIGHT = '''      /* Reject changes to a playing mux; wait until no active stream. */
      LIST_FOREACH(mm, &in->mn_muxes, mm_network_link) {
        im = (iptv_mux_t *)mm;
        if (im->mm_iptv_cuid && strcmp(im->mm_iptv_cuid, cuid) == 0 &&
            im->mm_active &&
            (url = htsmsg_get_str(item, "m3u-url")) &&
            strcmp(im->mm_iptv_url_sane ?: (im->mm_iptv_url ?: ""), url) != 0) {
          tvhinfo(LS_IPTV, "G3-AN URL change deferred for active stream");
          return -1;
        }
      }
'''
NEW_PREFLIGHT = '''      /* G3-AO: do not reject a URL config refresh solely because a mux
       * is active. IPTV input snapshots the running stream URL separately
       * in mm_iptv_url_raw at start; do not force-stop that input. */
'''
OLD_ACTIVE = '''        /* Do not change a currently playing stream in-place. */
        if (im->mm_active) goto end;
        iptv_url_set(&im->mm_iptv_url, &im->mm_iptv_url_sane,
'''
NEW_ACTIVE = '''        /* G3-AO: update config URL; current stream uses its own URL snapshot.
         * Next mux start will use the newly configured URL. */
        iptv_url_set(&im->mm_iptv_url, &im->mm_iptv_url_sane,
'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tree", type=Path)
    parser.add_argument("--apply", action="store_true")
    opts = parser.parse_args()
    root = opts.tree.resolve()
    if root != EXPECTED or not (root / ".git").exists():
        raise RuntimeError("WRONG_WORKTREE")
    target = root / "src/input/mpegts/iptv/iptv_auto.c"
    src = target.read_text(encoding="utf-8")
    for label, old, new in (
        ("ACTIVE_PREFLIGHT", OLD_PREFLIGHT, NEW_PREFLIGHT),
        ("ACTIVE_MATCH", OLD_ACTIVE, NEW_ACTIVE),
    ):
        if src.count(old) != 1 or new in src:
            raise RuntimeError("SOURCE_ANCHOR_MISMATCH_" + label)
        src = src.replace(old, new, 1)
    print("G3AO_ANCHORS=PASS")
    if not opts.apply:
        print("G3AO_APPLY=DRY_RUN")
        return
    tmp = target.with_name(target.name + ".g3ao-tmp")
    if tmp.exists():
        raise RuntimeError("TEMP_ALREADY_EXISTS")
    try:
        with tmp.open("x", encoding="utf-8") as writer:
            writer.write(src)
        tmp.chmod(target.stat().st_mode & 0o777)
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    print("G3AO_APPLY=PASS")

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print("G3AO=BLOCKED_" + str(error), file=sys.stderr)
        raise SystemExit(2)
