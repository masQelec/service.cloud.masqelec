#!/usr/bin/env python3
"""G3-AQ: read-only HTSP channel identity probe on isolated G3-AN.
Only 'hello' and 'enableAsyncMetadata' protocol calls. No Kodi profile access.
"""
import argparse
import json
import socket
import struct
import sys
import time

MAX_FRAME = 8 * 1024 * 1024
def field(name, kind, value):
    n = name.encode("utf-8")
    if kind == 3:
        data = value.encode("utf-8")
    elif kind == 2:
        if value < 0:
            raise ValueError("negative integer not supported")
        data = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "little")
    else:
        raise ValueError("unsupported request kind")
    return bytes((kind, len(n))) + struct.pack(">I", len(data)) + n + data

def send(sock, method, sequence):
    body = field("method", 3, method) + field("seq", 2, sequence)
    if method == "hello":
        body += field("htspversion", 2, 41)
        body += field("clientname", 3, "G3AQ-readonly-probe")
        body += field("clientversion", 3, "1")
    sock.sendall(struct.pack(">I", len(body)) + body)

def receive_exact(sock, length):
    buf = bytearray()
    while len(buf) < length:
        data = sock.recv(length - len(buf))
        if not data:
            raise EOFError("HTSP TCP connection closed")
        buf.extend(data)
    return bytes(buf)

def decode(data):
    result = {}
    offset = 0
    while offset < len(data):
        if offset + 6 > len(data):
            raise ValueError("truncated HTSMSG field header")
        kind, nlen = data[offset], data[offset + 1]
        length = struct.unpack_from(">I", data, offset + 2)[0]
        offset += 6
        if offset + nlen + length > len(data):
            raise ValueError("truncated HTSMSG field data")
        key = data[offset:offset + nlen].decode("utf-8", "replace")
        offset += nlen
        value = data[offset:offset + length]
        offset += length
        if kind == 3:
            result[key] = value.decode("utf-8", "replace")
        elif kind == 2:
            result[key] = int.from_bytes(value, "little")
        elif kind in (1, 5):
            result[key] = decode(value)
        elif kind == 4:
            result[key] = {"binary_bytes": len(value)}
        else:
            # Other fields irrelevant to channelId, but must retain frame alignment.
            result[key] = {"type": kind, "bytes": len(value)}
    return result

def receive(sock):
    length = struct.unpack(">I", receive_exact(sock, 4))[0]
    if length <= 0 or length > MAX_FRAME:
        raise ValueError(f"unexpected HTSP frame length: {length}")
    return decode(receive_exact(sock, length))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=39992)
    parser.add_argument("--timeout", type=float, default=18)
    args = parser.parse_args()
    channels = {}
    hello = False
    sync = False
    deadline = time.monotonic() + args.timeout
    try:
        with socket.create_connection((args.host, args.port), timeout=5) as sock:
            sock.settimeout(3)
            send(sock, "hello", 1)
            while time.monotonic() < deadline:
                try:
                    msg = receive(sock)
                except socket.timeout:
                    continue
                if msg.get("seq") == 1:
                    if msg.get("error") or msg.get("noaccess"):
                        raise RuntimeError("hello access error")
                    hello = True
                    print("G3AQ_HTSP_VERSION=" + str(msg.get("htspversion")), flush=True)
                    break
            if not hello:
                raise RuntimeError("no hello response")
            send(sock, "enableAsyncMetadata", 2)
            count = 0
            while time.monotonic() < deadline and count < 10000:
                try:
                    msg = receive(sock)
                except socket.timeout:
                    continue
                count += 1
                if msg.get("seq") == 2 and (msg.get("noaccess") or msg.get("error")):
                    raise RuntimeError("async metadata denied")
                method = msg.get("method")
                if method == "channelAdd":
                    row = {key: msg.get(key) for key in
                           ("channelId", "channelIdStr", "channelName",
                            "channelNumber") if key in msg}
                    if "channelId" in row:
                        channels[str(row["channelId"])] = row
                elif method in ("initialSyncCompleted", "initialSyncComplete"):
                    sync = True
                    break
    except Exception as exc:
        print("G3AQ_HTSP_PROBE=FAIL " + repr(exc), file=sys.stderr)
        return 2
    result = sorted(channels.values(), key=lambda x: x["channelId"])
    print("G3AQ_INITIAL_SYNC=" + ("PASS" if sync else "FAIL"))
    print("G3AQ_CHANNEL_COUNT=" + str(len(result)))
    print("G3AQ_CHANNELS_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    expected = {"e4852534cdb2fd64f54fd861d4d00767", "0d3bd243f67184e9adb9ceadf4a51c50"}
    observed = {str(x.get("channelIdStr", "")).replace("-", "").lower() for x in result}
    print("G3AQ_EXPECTED_UUIDS_PRESENT=" + str(expected <= observed))
    result_ok = sync and len(result) == 2 and expected <= observed and all(
        isinstance(x["channelId"], int) and x["channelId"] > 0 for x in result
    )
    print("G3AQ_HTSP_IDENTITY=" + ("PASS" if result_ok else "FAIL"))
    return 0 if result_ok else 1

if __name__ == "__main__":
    sys.exit(main())
