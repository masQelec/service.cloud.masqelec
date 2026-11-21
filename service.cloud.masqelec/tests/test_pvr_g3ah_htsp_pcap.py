"""G3-AH isolated synthetic HTSP/PCAP tests (no access to live services)."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3ah_htsp_pcap.py"
spec = importlib.util.spec_from_file_location("pvr_g3ah_htsp_pcap", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def field(typ, name, value):
    name = name.encode()
    return bytes([typ, len(name)]) + len(value).to_bytes(4, "big") + name + value


def htsp(method, name="G3AB Alpha Renamed"):
    raw = (field(3, "method", method.encode()) + field(2, "channelId", b"\x01")
           + field(3, "channelName", name.encode()))
    return len(raw).to_bytes(4, "big") + raw


def tcp_packet(sport, dport, seq, flags, payload=b""):
    import socket
    tcp = struct.pack("!HHIIHHHH", sport, dport, seq, 0,
                      (5 << 12) | flags, 4096, 0, 0) + payload
    ip = bytes([0x45, 0, 0, 20 + len(tcp), 0, 0, 0, 0, 64, 6, 0, 0])
    ip += socket.inet_aton("127.0.0.1") * 2
    return b"\0" * 12 + b"\x08\x00" + ip + tcp


def pcap(records):
    header = b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiiii", 2, 4, 0, 0, 262144, 1)
    return header + b"".join(
        struct.pack("<IIII", i + 1, 0, len(record), len(record)) + record
        for i, record in enumerate(records)
    )


class DecoderTests(unittest.TestCase):
    def test_htsp_map(self):
        self.assertEqual(m.fields(htsp("channelAdd")[4:]),
                         {"method": "channelAdd", "has_channel_id": True,
                          "has_channel_name": True})

    def test_never_expose_secret_fields(self):
        raw = (field(3, "method", b"channelUpdate")
               + field(3, "password", b"secret")
               + field(1, "nested", field(3, "token", b"PRIVATE")))
        result = m.fields(raw)
        self.assertEqual(result["method"], "channelUpdate")
        self.assertNotIn("secret", str(result))
        self.assertNotIn("PRIVATE", str(result))

    def test_invalid_field_size(self):
        with self.assertRaises(m.InvalidCapture):
            m.fields(bytes([3, 6, 0, 0, 5, 0]) + b"method")

    def test_invalid_field_type(self):
        with self.assertRaises(m.InvalidCapture):
            m.fields(field(99, "method", b"channelAdd"))

    def test_tcp_parse_direction(self):
        result = m.tcp_segment(tcp_packet(19992, 49262, 100, 0x18, b"data"))
        self.assertEqual(result[:4], ("server_to_client", 49262, 100, 0x18))
        self.assertEqual(result[4], b"data")

    def test_unrelated_port_ignored(self):
        self.assertIsNone(m.tcp_segment(tcp_packet(9982, 49262, 100, 0x18)))

    def test_fragmented_htsp(self):
        flow = m.Flow(100)
        payload = htsp("channelAdd")
        flow.feed(101, payload[:5])
        flow.feed(106, payload[5:])
        self.assertEqual(flow.counts["channelAdd"], 1)
        self.assertEqual(flow.frames, 1)

    def test_tcp_retransmission_deduplicated(self):
        flow = m.Flow(100)
        payload = htsp("channelAdd")
        flow.feed(101, payload)
        flow.feed(101, payload)
        self.assertEqual(flow.counts["channelAdd"], 1)

    def test_gap_blocks_inference(self):
        flow = m.Flow(100)
        flow.feed(900, htsp("channelAdd"))
        self.assertTrue(flow.gap)
        self.assertEqual(flow.frames, 0)

    def test_end_to_end_pcap(self):
        payload = htsp("channelAdd")
        records = [
            tcp_packet(49262, 19992, 10, 0x02),
            tcp_packet(19992, 49262, 100, 0x12),
            tcp_packet(19992, 49262, 101, 0x18, payload[:10]),
            tcp_packet(19992, 49262, 111, 0x18, payload[10:]),
        ]
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "synthetic.pcap"
            file.write_bytes(pcap(records))
            counts, sessions = m.analyze(file)
        self.assertEqual(counts["tcp_payload_packets"], 2)
        server = next(x for x in sessions if x["direction"] == "server_to_client")
        self.assertEqual(server["events"]["channelAdd"], 1)

    def test_invalid_pcap_magic(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.pcap"
            file.write_bytes(b"A" * 32)
            with self.assertRaises(m.InvalidCapture):
                list(m.packets(file))

    def test_no_payload_no_htsp_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "empty.pcap"
            file.write_bytes(pcap([tcp_packet(19992, 49262, 100, 0x12)]))
            stats, sessions = m.analyze(file)
        self.assertEqual(stats["tcp_payload_packets"], 0)
        self.assertEqual(sessions[0]["frames"], 0)


if __name__ == "__main__":
    unittest.main()
