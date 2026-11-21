#!/usr/bin/env python3
"""G3-AM synthetic-only persistent HTSP observer; never connects to production.

Protocol fields verified against Tvheadend 8837853a6 htsmsg_binary.c and
htsp_server.c. No subscription to playback/EPG and no auth credentials.
"""
import argparse
import socket
import struct
import sys
import time

MAX_FRAME = 4 * 1024 * 1024
MAX_FIELDS = 300
WATCH = {"channelAdd", "channelUpdate", "channelDelete", "initialSyncCompleted"}

def field(name, kind, value):
    n = name.encode("ascii")
    if kind == 3:
        b = value.encode("utf-8")
    elif kind == 2:
        b = value.to_bytes(max(1, (value.bit_length()+7)//8), "little")
    else:
        raise ValueError("INVALID_TYPE")
    return bytes((kind, len(n))) + struct.pack("!I", len(b)) + n + b

def send(sock, fields):
    body = b"".join(field(*item) for item in fields)
    sock.sendall(struct.pack("!I", len(body)) + body)

def read_exact(sock, count):
    out = bytearray()
    while len(out) < count:
        data = sock.recv(count-len(out))
        if not data:
            raise EOFError("HTSP_CLOSED")
        out.extend(data)
    return bytes(out)

def parse(body):
    out = {}
    offset = 0
    count = 0
    while offset < len(body):
        if len(body)-offset < 6:
            raise ValueError("TRUNCATED_FIELD")
        kind, nlen = body[offset], body[offset+1]
        size = int.from_bytes(body[offset+2:offset+6], "big")
        offset += 6
        if size > len(body)-offset-nlen:
            raise ValueError("OVERSIZE_FIELD")
        name = body[offset:offset+nlen].decode("ascii", "replace")
        offset += nlen
        data = body[offset:offset+size]
        offset += size
        count += 1
        if count > MAX_FIELDS:
            raise ValueError("TOO_MANY_FIELDS")
        if name in {"method", "channelName", "error"} and kind == 3:
            out[name] = data.decode("utf-8", "replace")[:160]
        elif name in {"channelId", "seq", "noaccess"} and kind == 2:
            out[name] = int.from_bytes(data, "little")
    return out

def run(seconds):
    if not 10 <= seconds <= 600:
        raise ValueError("DURATION_OUT_OF_RANGE")
    sock = socket.create_connection(("127.0.0.1", 29992), timeout=8)
    sock.settimeout(2)
    start = time.monotonic()
    observed = {k: 0 for k in WATCH}
    names_by_id = {}
    initialized = False
    try:
        send(sock, [("method", 3, "hello"), ("htspversion", 2, 34),
                    ("clientname", 3, "masQelec-G3AM-watch"),
                    ("seq", 2, 1)])
        send(sock, [("method", 3, "enableAsyncMetadata"), ("epg", 2, 0),
                    ("seq", 2, 2)])
        print("G3AM_HTSP_CONNECTED=YES", flush=True)
        print("G3AM_HTSP_WAITING_FOR_INITIAL_SYNC=YES", flush=True)
        while time.monotonic() - start < seconds:
            try:
                header = read_exact(sock, 4)
                length = int.from_bytes(header, "big")
                if not 6 <= length <= MAX_FRAME:
                    raise ValueError("INVALID_HTSP_FRAME_LENGTH")
                msg = parse(read_exact(sock, length))
            except socket.timeout:
                continue
            method = msg.get("method")
            if "error" in msg:
                raise RuntimeError("HTSP_ERROR=" + msg["error"])
            if method not in WATCH:
                continue
            observed[method] += 1
            if method == "initialSyncCompleted":
                initialized = True
                print("G3AM_HTSP_INITIAL_SYNC=PASS", flush=True)
                print("G3AM_HTSP_READY_FOR_RENAME=YES", flush=True)
                continue
            channel_id = msg.get("channelId")
            channel_name = msg.get("channelName")
            if channel_id is not None and channel_name is not None:
                names_by_id[channel_id] = channel_name
            print("HTSP_EVENT=" + method +
                  " ID=" + str(channel_id) +
                  " NAME=" + str(channel_name if channel_name is not None else names_by_id.get(channel_id, "UNSPECIFIED")) +
                  " PHASE=" + ("AFTER_SYNC" if initialized else "INITIAL"),
                  flush=True)
    finally:
        sock.close()
        print("G3AM_HTSP_SUMMARY=" + str(observed), flush=True)
        print("G3AM_HTSP_OBSERVER_DONE=YES", flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=180)
    args = p.parse_args()
    try:
        run(args.seconds)
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        print("G3AM_HTSP_WATCH=FAIL_" + str(exc), file=sys.stderr)
        sys.exit(2)
