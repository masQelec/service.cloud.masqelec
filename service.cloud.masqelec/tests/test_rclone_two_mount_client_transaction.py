# -*- coding: utf-8 -*-
"""Transaction protocol tests: no real Kodi, OAuth or systemd."""
import unittest

from lib import rclone_two_mount_client_transaction as tx


def candidate():
    return {"status": "candidate_requires_probe",
            "account_index": 0, "baseline_account": b"old",
            "candidate_account": b"new"}


class FakeOps:
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []
    def _step(self, name, index, *args):
        self.calls.append((name, index))
        return name != self.fail
    def snapshot(self, i, expected):
        return self._step("snapshot", i, expected)
    def stop(self, i):
        return self._step("stop", i)
    def quiescent(self, i):
        return self._step("quiescent", i)
    def still_current(self, i, old):
        return self._step("still_current", i, old)
    def install(self, i, new):
        return self._step("install", i, new)
    def start(self, i):
        return self._step("start", i)
    def healthy(self, i):
        return self._step("healthy", i)
    def commit(self, i):
        return self._step("commit", i)
    def rollback(self, i):
        return self._step("rollback", i)
    def rollback_healthy(self, i):
        return self._step("rollback_healthy", i)


class ClientTransactionTests(unittest.TestCase):
    def invoke(self, ops, **kwargs):
        args = dict(authorized=True, verified_probe=True,
                    playback_idle=True, operations=ops)
        args.update(kwargs)
        return tx.execute(candidate(), **args)

    def test_disabled_performs_zero_operations(self):
        ops = FakeOps()
        self.assertEqual(self.invoke(ops, authorized=False),
                         "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(ops.calls, [])

    def test_playback_or_unverified_fails_closed(self):
        for change in (dict(playback_idle=False),
                       dict(verified_probe=False)):
            ops = FakeOps()
            self.assertEqual(self.invoke(ops, **change),
                             "BLOCKED_UNVERIFIED_OR_PLAYBACK")
            self.assertEqual(ops.calls, [])

    def test_requires_complete_adapter(self):
        self.assertEqual(tx.execute(candidate(), authorized=True,
                                    verified_probe=True, playback_idle=True),
                         "BLOCKED_OPERATIONS")

    def test_success_stays_on_single_account(self):
        ops = FakeOps()
        self.assertEqual(self.invoke(ops), "RECOVERED_VERIFIED")
        self.assertEqual([name for name, _ in ops.calls],
                         ["snapshot", "stop", "quiescent", "still_current",
                          "install", "start", "healthy", "commit"])
        self.assertEqual(set(i for _, i in ops.calls), {0})

    def test_snapshot_fail_never_stops(self):
        ops = FakeOps("snapshot")
        self.assertEqual(self.invoke(ops), "BLOCKED_SNAPSHOT")
        self.assertEqual(ops.calls, [("snapshot", 0)])

    def test_every_failure_rolls_back(self):
        for name in ("stop", "quiescent", "still_current", "install",
                     "start", "healthy", "commit"):
            with self.subTest(stage=name):
                ops = FakeOps(name)
                self.assertEqual(self.invoke(ops), "ROLLED_BACK_VERIFIED")
                self.assertIn(("rollback", 0), ops.calls)
                self.assertEqual(ops.calls[-1], ("rollback_healthy", 0))
                self.assertNotIn(("commit", 1), ops.calls)

    def test_unverifiable_rollback_requires_manual(self):
        for name in ("rollback", "rollback_healthy"):
            ops = FakeOps(name)
            original = ops.install
            ops.install = lambda i, v: False
            self.assertEqual(self.invoke(ops),
                             "MANUAL_RECOVERY_REQUIRED")

    def test_untrusted_candidate_cannot_start(self):
        ops = FakeOps()
        for item in ({}, {"status": "candidate_requires_probe",
                          "account_index": True, "baseline_account": b"a",
                          "candidate_account": b"b"}):
            self.assertEqual(tx.execute(item, authorized=True,
                                        verified_probe=True,
                                        playback_idle=True, operations=ops),
                             "BLOCKED_CANDIDATE")
        self.assertEqual(ops.calls, [])


if __name__ == "__main__":
    unittest.main()
