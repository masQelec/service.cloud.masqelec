#!/usr/bin/env python3
"""G3-AM destructive-to-synthetic-playlist ONLY, gated Tvheadend/Kodi PVR matrix.

Never edits TVH config, Kodi DB, G3-AB playlist or addon state.
Stops at first unexpected identity or channel result. Requires a live lab Kodi.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import urllib.request

BASE = Path(__file__).resolve().parents[1] / "lab/pvr_g3ab/runtime"
PRIVATE = BASE / "g3am"
PLAYLIST = PRIVATE / "playlist/playlist.m3u"
MARKER = BASE / ".g3ab-synthetic-only"
DB = PRIVATE / "kodi_home/.kodi/userdata/Database/TV46.db"
API = "http://127.0.0.1:29991/api/"
A_UUID = "beec46e5ab595d2474289e74c9ab9849"
B_UUID = "2591ccd729867bffc24e8f4bd8b765af"
A_ID = 1699146942
B_ID = 1473024293
A_KODI = 2
B_KODI = 1
WAIT = 150

def api(endpoint):
    with urllib.request.urlopen(API + endpoint, timeout=7) as reply:
        return json.load(reply)["entries"]

def snapshots():
    cs = api("channel/grid?all=1")
    services = api("mpegts/service/grid?all=1")
    with sqlite3.connect("file:" + str(DB) + "?mode=ro",
                         uri=True, timeout=5) as con:
        ks = con.execute("SELECT idChannel,iUniqueId,sChannelName FROM channels ORDER BY idChannel").fetchall()
    return cs, services, ks

def guard():
    if not MARKER.is_file() or MARKER.is_symlink():
        raise RuntimeError("SYNTHETIC_MARKER_MISSING")
    if MARKER.read_text() != "masqelec-g3ab-synthetic-v1\n":
        raise RuntimeError("SYNTHETIC_MARKER_MISMATCH")
    for f in (PRIVATE, PRIVATE / "playlist", PRIVATE / "tvh_config", PRIVATE / "kodi_home", DB.parent):
        if not f.is_dir() or f.is_symlink():
            raise RuntimeError("INVALID_PRIVATE_DIR_" + f.name)
    if not PLAYLIST.is_file() or PLAYLIST.is_symlink() or DB.is_symlink():
        raise RuntimeError("INVALID_PRIVATE_FILES")
    if PLAYLIST.stat().st_uid != os.getuid():
        raise RuntimeError("PLAYLIST_OWNER_MISMATCH")
    if "g3am-001" not in PLAYLIST.read_text() or "g3am-002" not in PLAYLIST.read_text():
        raise RuntimeError("CURRENT_PLAYLIST_NOT_G3AM")
    import socket
    with socket.create_connection(("127.0.0.1", 29992), timeout=3):
        pass
    # Check current Kodi session is connected to this Tvheadend, not merely running.
    with Path("/proc/net/tcp").open() as f:
        tcp = f.read()
    if ":7528" not in tcp.upper():  # hex 29992
        raise RuntimeError("HTSP_PORT_NOT_SEEN")
    cs, _, ks = snapshots()
    if {c["uuid"] for c in cs} != {A_UUID, B_UUID}:
        raise RuntimeError("TVH_BASELINE_UUID_MISMATCH")
    if len(ks) != 2 or {(r[0], r[1]) for r in ks} != {(A_KODI, A_ID), (B_KODI, B_ID)}:
        raise RuntimeError("KODI_BASELINE_ID_MISMATCH")
    return cs, ks

def entry(key, title, number, group, url):
    return ('#EXTINF:-1 CUID="g3am-' + key +
            '" tvg-chno="' + str(number) + '" tvh-chnum="' + str(number) +
            '" tvg-name="' + title + '" group-title="' + group + '",' + title + "\n" + url + "\n")

def m3u(stage):
    a = entry("001", "G3AM Alpha Renamed", 1, "G3AM SYNTHETIC", "http://streams/ch1.ts")
    b = entry("002", "G3AM Beta", 2, "G3AM SYNTHETIC", "http://streams/ch2.ts")
    if stage == "reorder":
        return "#EXTM3U\n" + b + a
    if stage == "group":
        return "#EXTM3U\n" + entry("001", "G3AM Alpha Renamed", 1, "G3AM GROUP NEW", "http://streams/ch1.ts") + b
    if stage == "url":
        # Same transport bytes, distinct URL with harmless query; tests mux identity matching.
        return "#EXTM3U\n" + entry("001", "G3AM Alpha Renamed", 1, "G3AM SYNTHETIC", "http://streams/ch1.ts?g3am_url_test=1") + b
    if stage == "add":
        return "#EXTM3U\n" + a + b + entry("003", "G3AM Gamma", 3, "G3AM SYNTHETIC", "http://streams/ch1.ts?g3am_gamma=1")
    if stage == "remove":
        return "#EXTM3U\n" + a  # removing Beta is deliberately an exploratory gate
    if stage == "restore":
        return "#EXTM3U\n" + a + b
    raise ValueError(stage)

def atomic_publish(stage):
    payload = m3u(stage)
    fd, tmp = tempfile.mkstemp(prefix=".g3am-matrix-", dir=PLAYLIST.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, PLAYLIST)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("MATRIX_STAGE=" + stage + " PLAYLIST_ONLY=YES", flush=True)

def identity(cs, ks, alpha="G3AM Alpha Renamed", beta="G3AM Beta"):
    cc = {c["uuid"]: c for c in cs}
    if set(cc) != {A_UUID, B_UUID}:
        return False, "TVH_UUID_SET"
    if cc[A_UUID]["name"] != alpha or cc[B_UUID]["name"] != beta:
        return False, "TVH_NAMES"
    if cc[A_UUID].get("number") != 1 or cc[B_UUID].get("number") != 2:
        return False, "TVH_NUMBERS"
    expect = [(B_KODI, B_ID, beta), (A_KODI, A_ID, alpha)]
    if ks != expect:
        return False, "KODI_CHANNELS"
    return True, "STABLE"

def wait_for(stage, max_seconds=WAIT):
    previous = None
    start = time.monotonic()
    while time.monotonic() - start < max_seconds:
        cs, services, ks = snapshots()
        good, reason = identity(cs, ks)
        status = (good, reason, len(cs), len(services), tuple(ks))
        if status != previous:
            print("OBSERVE stage=%s t=%ds tvh=%d services=%d kodi=%s reason=%s" %
                  (stage, int(time.monotonic()-start), len(cs), len(services),
                   repr(ks), reason), flush=True)
            previous = status
        if stage in ("reorder", "group", "restore") and good:
            # Identity alone does NOT prove refetch happened, nor tag/order update.
            return "IDENTITY_ONLY"
        if stage == "url" and (not good or len(services) > 3):
            return "REVIEW_URL"
        if stage == "add" and len(ks) >= 3:
            return "REVIEW_ADD"
        if stage == "remove" and len(ks) < 2:
            return "REVIEW_REMOVE"
        time.sleep(5)
    return "TIMEOUT"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--run", choices=["safe", "all"])
    args = parser.parse_args()
    if not (args.preflight or args.run):
        parser.error("choose --preflight or --run safe|all")
    cs, ks = guard()
    good, reason = identity(cs, ks)
    if not good:
        raise RuntimeError("INITIAL_RENAME_STATE_REQUIRED_" + reason)
    print("G3AM_MATRIX_PREFLIGHT=PASS", flush=True)
    if args.preflight:
        return 0
    # Safe stages are a churn smoke test: they assert only identity, never false PASS for group/order.
    for stage in ("reorder", "group", "restore"):
        atomic_publish(stage)
        # Wait for a full 75s to include one expected 60s IPTV refetch.
        time.sleep(75)
        outcome = wait_for(stage, 10)
        print("STAGE=%s RESULT=%s" % (stage, outcome), flush=True)
        if outcome != "IDENTITY_ONLY":
            print("G3AM_MATRIX=STOP_" + stage, flush=True)
            return 2
    print("G3AM_SAFE_IDENTITY=PASS", flush=True)
    print("G3AM_GROUP_AND_ORDER_PROPAGATION=UNVERIFIED", flush=True)
    if args.run == "safe":
        return 0
    # Risky stages: observe one at a time, stop on first ambiguous/disruptive result.
    # Never automatically delete/recreate TVH channels or SQLite entries.
    for stage in ("url", "add", "remove"):
        atomic_publish(stage)
        outcome = wait_for(stage)
        print("STAGE=%s RESULT=%s" % (stage, outcome), flush=True)
        print("G3AM_MATRIX=STOP_FOR_OPERATOR_REVIEW", flush=True)
        return 3
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as e:
        print("G3AM_MATRIX=BLOCKED_" + str(e), file=sys.stderr)
        sys.exit(2)
