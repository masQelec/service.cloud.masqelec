# -*- coding: utf-8 -*-
"""CLIENT crash recovery across two independent Python processes.

Files are fake /tmp fixtures. No Kodi, OAuth, systemd or real rclone access.
The first process deliberately exits with an interrupted durable transaction;
the second restores it through the same production journal recovery API.
"""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ADDON = str(Path(__file__).resolve().parents[1])
STEP = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from lib import rclone_two_mount_client_crash_recovery as crash
from lib import rclone_two_mount_client_file_ops as files

root = Path(sys.argv[2])
config = root / "configs"
journal = root / "account1"
account = config / "account1.conf"
other = config / "account2.conf"
phase = sys.argv[3]
if phase == "interrupt":
    for folder in (config, journal):
        folder.mkdir(mode=0o700)
        folder.chmod(0o700)
    for file, content in ((account, b"fake-before"), (other, b"other-untouched")):
        fd = os.open(str(file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
    class Initial:
        def snapshot(self, i, expected):
            self.ops = files.AccountFileOps(
                0, account_path=str(account), journal_dir=str(journal),
                stop=lambda j: True, quiescent=lambda j: True,
                start=lambda j: True, healthy=lambda j: True, enabled=True)
            return self.ops.snapshot(i, expected)
    initial = Initial()
    with files.locked(str(journal)):
        assert initial.snapshot(0, b"fake-before")
        assert initial.ops.stop(0)
        assert initial.ops.quiescent(0)
        assert initial.ops.still_current(0, b"fake-before")
        assert initial.ops.install(0, b"fake-after")
    assert files.recovery_pending(str(journal), 0)
    assert account.read_bytes() == b"fake-after"
    # Process exits without start, health check or commit.
    sys.exit(0)
elif phase == "recover":
    class Services:
        def stop(self, i): return i == 0
        def quiescent(self, i): return i == 0
        def start(self, i): return i == 0
        def healthy(self, i): return i == 0
    result = crash.restore_interrupted(
        0, account_path=str(account), journal_dir=str(journal),
        services=Services(), authorized=True)
    assert result == "ROLLED_BACK_VERIFIED", result
    assert account.read_bytes() == b"fake-before"
    assert other.read_bytes() == b"other-untouched"
    assert not files.recovery_pending(str(journal), 0)
    assert json.loads((journal / "state.json").read_text())["phase"] == "rolled_back"
    sys.exit(0)
else:
    sys.exit(2)
'''


class RestartProcessTests(unittest.TestCase):
    def test_independent_processes_restore_interrupted_client_journal(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-process-recovery-") as temp:
            root = Path(temp)
            first = subprocess.run(
                [sys.executable, "-c", STEP, ADDON, str(root), "interrupt"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=15)
            self.assertEqual(first.returncode, 0, first.stderr.decode("utf-8", "replace"))
            path = root / "account1" / "state.json"
            self.assertEqual(json.loads(path.read_text())["phase"],
                             "install_requested")
            second = subprocess.run(
                [sys.executable, "-c", STEP, ADDON, str(root), "recover"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=15)
            self.assertEqual(second.returncode, 0, second.stderr.decode("utf-8", "replace"))
            self.assertEqual(stat.S_IMODE((root / "configs" / "account1.conf").stat().st_mode),
                             0o600)


if __name__ == "__main__":
    unittest.main()
