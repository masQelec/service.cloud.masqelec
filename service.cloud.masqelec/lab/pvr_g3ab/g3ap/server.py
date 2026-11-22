#!/usr/bin/env python3
"""Isolated synthetic MPEG-TS HTTP loop, only for the G3-AP lab.

Do not use with public networks. Paths are fixed and source is mounted read-only.
One ffmpeg subprocess per client; current TS kept intact when playlist URL changes.
"""
import os
from pathlib import Path
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

SOURCE = Path("/source")
ALLOWED = {"/ch1.ts": SOURCE / "ch1.ts", "/ch2.ts": SOURCE / "ch2.ts"}
CHUNK = 188 * 32
MAX_CLIENTS = threading.BoundedSemaphore(6)

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"OK\n")
            return
        # Query may change without changing synthetic media.
        path = self.path.split("?", 1)[0]
        source = ALLOWED.get(path)
        if source is None:
            self.send_error(404)
            return
        if not source.is_file():
            self.send_error(503, "source TS missing")
            return
        if not MAX_CLIENTS.acquire(blocking=False):
            self.send_error(503, "synthetic client limit reached")
            return
        proc = None
        total = 0
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-re", "-stream_loop", "-1", "-i", str(source),
                "-map", "0:v:0", "-map", "0:a:0",
                "-c", "copy", "-f", "mpegts", "pipe:1",
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=None, stdin=subprocess.DEVNULL,
            )
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                block = os.read(proc.stdout.fileno(), CHUNK)
                if not block:
                    break
                self.wfile.write(block)
                total += len(block)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError) as exc:
            print(f"G3AP_CLIENT_END path={path} bytes={total} kind={type(exc).__name__}", flush=True)
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
                if proc.stdout:
                    proc.stdout.close()
            MAX_CLIENTS.release()

    def log_message(self, fmt, *args):
        print(f"G3AP_HTTP client={self.client_address[0]} " + fmt % args, flush=True)

if __name__ == "__main__":
    for path in ALLOWED.values():
        if not path.is_file():
            raise SystemExit(f"G3AP_SOURCE_MISSING={path.name}")
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.daemon_threads = True
    print("G3AP_LISTEN=0.0.0.0:8080", flush=True)
    server.serve_forever(poll_interval=0.25)
