#!/usr/bin/env python3
"""G3-AH: bounded offline decoder of HTSP frames in classic Ethernet/IPv4/TCP PCAP.
Read-only. Never prints payload, channel names/IDs, URLs, secrets or IP addresses.
"""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import struct

MAX_CAPTURE = 32 * 1024 * 1024
MAX_MESSAGE = 4 * 1024 * 1024
WATCH = frozenset(("channelAdd", "channelUpdate", "channelDelete",
                   "subscriptionStart", "initialSyncCompleted",
                   "tagAdd", "tagUpdate", "tagDelete"))


class InvalidCapture(ValueError):
    pass


def packets(path):
    if not path.is_file() or path.stat().st_size > MAX_CAPTURE:
        raise InvalidCapture("MISSING_OR_OVERSIZE_CAPTURE")
    with path.open("rb") as f:
        hdr = f.read(24)
        if len(hdr) != 24:
            raise InvalidCapture("TRUNCATED_PCAP_HEADER")
        magic = hdr[:4]
        if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
            end = "<"
        elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
            end = ">"
        else:
            raise InvalidCapture("UNSUPPORTED_PCAP_MAGIC")
        major, minor, _, _, snaplen, network = struct.unpack(end + "HHiiii", hdr[4:])
        if (major, minor) != (2, 4) or network != 1 or not 64 <= snaplen <= 262144:
            raise InvalidCapture("UNSUPPORTED_PCAP_FORMAT")
        while True:
            header = f.read(16)
            if not header:
                return
            if len(header) != 16:
                raise InvalidCapture("TRUNCATED_PACKET_HEADER")
            _, _, included, original = struct.unpack(end + "IIII", header)
            if not 0 < included <= snaplen or included > original:
                raise InvalidCapture("INVALID_PACKET_LENGTH")
            raw = f.read(included)
            if len(raw) != included:
                raise InvalidCapture("TRUNCATED_PACKET")
            yield raw


def tcp_segment(raw):
    if len(raw) < 14 or raw[12:14] != b"\x08\x00":
        return None
    ip = raw[14:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
        return None
    ihl = (ip[0] & 15) * 4
    if ihl < 20 or len(ip) < ihl:
        return None
    total = int.from_bytes(ip[2:4], "big")
    if total < ihl + 20 or len(ip) < total or int.from_bytes(ip[6:8], "big") & 0x3fff:
        return None
    seg = ip[ihl:total]
    sport, dport, seq = struct.unpack("!HHI", seg[:8])
    if sport != 19992 and dport != 19992:
        return None
    hlen = (seg[12] >> 4) * 4
    if hlen < 20 or hlen > len(seg):
        return None
    return ("server_to_client" if sport == 19992 else "client_to_server",
            dport if sport == 19992 else sport, seq, seg[13], seg[hlen:])


def fields(data, depth=0):
    """Parse full binary htsmsg; return only allowlisted presence/type metadata."""
    if depth > 5:
        raise InvalidCapture("MAX_NESTING")
    offset, count, found = 0, 0, {}
    while offset < len(data):
        if len(data) - offset < 6:
            raise InvalidCapture("TRUNCATED_HTSMSG_FIELD")
        typ, nlen = data[offset], data[offset + 1]
        size = int.from_bytes(data[offset + 2:offset + 6], "big")
        offset += 6
        if size > len(data) - offset - nlen:
            raise InvalidCapture("INVALID_HTSMSG_FIELD_SIZE")
        name = data[offset:offset + nlen]
        offset += nlen
        value = data[offset:offset + size]
        offset += size
        count += 1
        if count > 300 or typ not in (1, 2, 3, 4, 5, 7, 8):
            raise InvalidCapture("INVALID_HTSMSG_TYPE_OR_COUNT")
        if typ in (1, 5):
            fields(value, depth + 1)
        if typ == 3 and name == b"method":
            found["method"] = value.decode("utf-8", "replace") if len(value) < 80 else ""
        elif typ == 3 and name == b"channelName":
            found["has_channel_name"] = True
        elif typ == 2 and name == b"channelId":
            found["has_channel_id"] = True
    return found


class Flow:
    def __init__(self, seq):
        self.next_seq = (seq + 1) & 0xffffffff
        self.buffer = bytearray()
        self.frames = 0
        self.invalid = 0
        self.gap = False
        self.counts = Counter()

    def feed(self, seq, payload):
        if not payload or self.gap:
            return
        delta = (seq - self.next_seq) & 0xffffffff
        if delta >= 0x80000000:
            duplicate = (self.next_seq - seq) & 0xffffffff
            if duplicate >= len(payload):
                return
            payload = payload[duplicate:]
        elif delta:
            self.gap = True
            return
        self.next_seq = (self.next_seq + len(payload)) & 0xffffffff
        self.buffer.extend(payload)
        while len(self.buffer) >= 4:
            length = int.from_bytes(self.buffer[:4], "big")
            if length > MAX_MESSAGE or length < 6:
                self.invalid += 1
                self.gap = True
                return
            if len(self.buffer) < length + 4:
                break
            raw = bytes(self.buffer[4:length + 4])
            del self.buffer[:length + 4]
            try:
                metadata = fields(raw)
            except InvalidCapture:
                self.invalid += 1
                continue
            self.frames += 1
            method = metadata.get("method", "")
            if method in WATCH:
                self.counts[method] += 1
                if method in ("channelAdd", "channelUpdate"):
                    if metadata.get("has_channel_name"):
                        self.counts[method + "_with_name"] += 1
                    if metadata.get("has_channel_id"):
                        self.counts[method + "_with_id"] += 1


def analyze(path):
    sessions, stats = defaultdict(list), Counter()
    for raw in packets(path):
        item = tcp_segment(raw)
        if item is None:
            continue
        direction, port, seq, flags, payload = item
        stats["tcp_packets"] += 1
        if payload:
            stats["tcp_payload_packets"] += 1
        key = direction, port
        if flags & 0x02:
            sessions[key].append(Flow(seq))
            stats["syn_packets"] += 1
        if not sessions[key]:
            stats["midstream_packets"] += 1
            continue
        if payload:
            sessions[key][-1].feed((seq + (1 if flags & 2 else 0)) & 0xffffffff, payload)
    reports = []
    for (direction, port), flows in sorted(sessions.items()):
        for number, flow in enumerate(flows, 1):
            reports.append({"direction": direction, "client_port": port,
                            "session_number": number, "frames": flow.frames,
                            "invalid_frames": flow.invalid,
                            "gap_or_desync": flow.gap,
                            "events": dict(sorted(flow.counts.items()))})
    return stats, reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pcap", type=Path)
    args = parser.parse_args()
    try:
        stats, sessions = analyze(args.pcap)
    except (OSError, InvalidCapture) as exc:
        print("G3AH=BLOCKED_" + (str(exc) if isinstance(exc, InvalidCapture)
                                else "IO_ERROR"))
        return 2
    print("G3AH=OFFLINE_OBSERVATION")
    for key in ("tcp_packets", "tcp_payload_packets", "syn_packets", "midstream_packets"):
        print(key.upper() + "=" + str(stats[key]))
    for session in sessions:
        print("SESSION=" + str(session))
    print("G3AH_AUTH_CONTENT_PRINTED=NO")
    print("G3AH_HTSP_RECEIVED_BY_PVR_PROVEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
