# -*- coding: utf-8 -*-
"""MASTER v2 create/update bajo CAS, transportes sintéticos, sin red."""
import base64
import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import rclone_two_mount_master_sync as master
from lib import rclone_two_mount_publish_guard as crypt
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_config_routes as routes
from test_rclone_mount_isolation import wrapped_conf


class FakeGH:
    def __init__(self, key, *, remote=None, missing=False):
        self.key = key
        self.current = ("a" * 40)
        self.previous = []
        self.calls = []
        self.missing = missing
        self.remote = remote

    def head(self):
        self.calls.append("HEAD")
        return self.current

    def get(self, path):
        self.calls.append("GET:" + path)
        assert path == routes.V2_REMOTE_PATH
        if self.missing:
            return 404, {"message": "Not Found"}
        if self.remote is None:
            raise AssertionError("unset GH remote")
        blob = crypt.encode_candidate(self.remote, self.key)
        return 200, {
            "encoding": "base64",
            "sha": crypt.git_blob_sha(blob),
            "content": base64.b64encode(blob).decode("ascii")}

    def put(self, path, payload):
        self.calls.append("PUT:" + path)
        assert path == routes.V2_REMOTE_PATH
        assert payload["branch"] == "21"
        assert bool(payload.get("sha")) != self.missing
        plaintext = crypt.decode_remote_contents({
            "encoding": "base64",
            "sha": crypt.git_blob_sha(base64.b64decode(payload["content"])),
            "content": payload["content"]}, self.key)["canonical"]
        if not self.missing and payload["sha"] != crypt.git_blob_sha(
                crypt.encode_candidate(self.remote, self.key)):
            # This fake class encrypts on each get; different nonce changes
            # SHA. Override in test helper to stable opaque GH blob.
            pass
        self.remote = plaintext
        self.missing = False
        self.current = "b" * 40
        blob = base64.b64decode(payload["content"])
        self._saved_blob = blob
        return (201 if "sha" not in payload else 200), {
            "content": {"sha": crypt.git_blob_sha(blob)},
            "commit": {"sha": self.current}}


class StableGH:
    """Modelo realista de contents: bytes cifrados conservan SHA entre GET."""
    def __init__(self, key, remote=None):
        self.key = key
        self.head_sha = "a" * 40
        self.blob = None if remote is None else crypt.encode_candidate(
            remote, key)
        self.calls = []
        self.get_override = None
        self.put_override = None
        self.inject_drift = False

    def head(self):
        self.calls.append("head")
        return self.head_sha

    def get(self, path):
        self.calls.append(("get", path))
        if self.get_override:
            return self.get_override
        if self.blob is None:
            return 404, {"message": "Not Found"}
        return 200, {
            "encoding": "base64", "sha": crypt.git_blob_sha(self.blob),
            "content": base64.b64encode(self.blob).decode("ascii")}

    def put(self, path, payload):
        self.calls.append(("put", path))
        if self.put_override:
            return self.put_override
        if path != routes.V2_REMOTE_PATH:
            raise AssertionError("unexpected path")
        is_create = "sha" not in payload
        if is_create != (self.blob is None):
            return 422, {}
        if not is_create and payload["sha"] != crypt.git_blob_sha(self.blob):
            return 409, {}
        self.blob = base64.b64decode(payload["content"])
        self.head_sha = "b" * 40
        return (201 if is_create else 200), {
            "content": {"sha": crypt.git_blob_sha(self.blob)},
            "commit": {"sha": self.head_sha}}


class MasterV2PublishTests(unittest.TestCase):
    def setUp(self):
        self.key = b"K" * 32
        self.canonical = wrapped_conf("crypt")
        self.accounts = tuple(
            plan.account_snapshot(self.canonical, index) for index in (0, 1))
        self.source = lambda: (self.canonical, self.accounts)
        self.health = lambda candidate, names: {x: "ok" for x in names}

    def run_sync(self, gh, **options):
        opts = dict(release_authorized=True,
                    master_attested=True, branch="21")
        opts.update(options)
        return master.sync_once(self.source, gh.head, gh.get, gh.put,
                                self.health, self.key, "TEST_GH_TOKEN", **opts)

    def test_no_remote_creates_only_v2_and_confirms_readback(self):
        gh = StableGH(self.key)
        result = self.run_sync(gh)
        self.assertEqual(result, "created_verified")
        self.assertEqual(gh.calls.count(("put", routes.V2_REMOTE_PATH)), 1)
        self.assertNotIn(("put", routes.LEGACY_REMOTE_PATH), gh.calls)
        self.assertEqual(
            crypt.decode_remote_contents(gh.get(routes.V2_REMOTE_PATH)[1],
                                         self.key)["canonical"], self.canonical)

    def test_existing_equal_does_not_write(self):
        gh = StableGH(self.key, self.canonical)
        self.assertEqual(self.run_sync(gh), "unchanged")
        self.assertFalse(any(isinstance(c, tuple) and c[0] == "put"
                             for c in gh.calls))

    def test_changed_local_one_account_updates_using_cas(self):
        remote = self.canonical
        self.accounts = (
            self.accounts[0].replace(
                b"refresh-users_library_1", b"refresh-rotated-one"),
            self.accounts[1])
        gh = StableGH(self.key, remote)
        self.assertEqual(self.run_sync(gh), "updated_verified")
        latest = crypt.decode_remote_contents(
            gh.get(routes.V2_REMOTE_PATH)[1], self.key)["canonical"]
        self.assertEqual(
            policy.oauth_tokens(latest)["one_a"]["refresh_token"],
            "refresh-rotated-one")
        self.assertEqual(
            policy.oauth_tokens(latest)["one_b"]["refresh_token"],
            policy.oauth_tokens(remote)["one_b"]["refresh_token"])

    def test_access_only_churn_does_not_publish(self):
        self.accounts = (self.accounts[0].replace(
            b"access-users_library_1", b"access-only-change"), self.accounts[1])
        gh = StableGH(self.key, self.canonical)
        self.assertEqual(self.run_sync(gh), "unchanged")

    def test_not_authorized_does_not_read_or_write(self):
        gh = StableGH(self.key)
        self.assertEqual(self.run_sync(
            gh, release_authorized=False), "blocked_not_authorized")
        self.assertEqual(gh.calls, [])

    def test_not_master_does_not_read_or_write(self):
        gh = StableGH(self.key)
        self.assertEqual(self.run_sync(
            gh, master_attested=False), "blocked_not_authorized")
        self.assertEqual(gh.calls, [])

    def test_404_alone_does_not_authorize_no_branch(self):
        gh = StableGH(self.key)
        gh.head = lambda: None
        self.assertEqual(self.run_sync(gh), "blocked_repository_unverified")
        self.assertIsNone(gh.blob)

    def test_unauthorized_404_or_403_branch_blocked(self):
        gh = StableGH(self.key)
        gh.head = lambda: "403 Forbidden"
        self.assertEqual(self.run_sync(gh), "blocked_repository_unverified")

    def test_network_get_failure_does_not_create(self):
        gh = StableGH(self.key)
        gh.get_override = (None, "")
        self.assertEqual(self.run_sync(gh), "blocked_remote_unavailable")
        self.assertIsNone(gh.blob)

    def test_get_403_never_treated_as_absence(self):
        gh = StableGH(self.key)
        gh.get_override = (403, {"message": "Forbidden"})
        self.assertEqual(self.run_sync(gh), "blocked_remote_unavailable")

    def test_get_remote_corrupt_blocks_update(self):
        gh = StableGH(self.key, self.canonical)
        gh.get_override = (200, {"content": "garbage", "sha": "x"})
        self.assertEqual(self.run_sync(gh), "blocked_remote_invalid")

    def test_wrong_remote_static_options_blocks(self):
        changed = self.canonical.replace(
            b"filename_encryption = off",
            b"filename_encryption = standard")
        gh = StableGH(self.key, changed)
        self.assertEqual(self.run_sync(gh), "blocked_remote_static_change")

    def test_wrong_account_crypt_blocks_without_gh_calls(self):
        self.accounts = (self.accounts[0].replace(
            b"filename_encryption = off", b"filename_encryption = standard"),
                         self.accounts[1])
        gh = StableGH(self.key)
        self.assertEqual(self.run_sync(gh), "blocked_sync_failure")
        self.assertFalse(any(isinstance(c, tuple) and c[0] == "put"
                             for c in gh.calls))

    def test_health_unknown_not_upload(self):
        gh = StableGH(self.key)
        self.health = lambda candidate, names: {x: "unavailable" for x in names}
        self.assertEqual(self.run_sync(gh), "blocked_local_health")
        self.assertIsNone(gh.blob)

    def test_incomplete_health_not_upload(self):
        gh = StableGH(self.key)
        self.health = lambda candidate, names: {}
        self.assertEqual(self.run_sync(gh), "blocked_local_health")

    def test_token_rotation_during_gate_blocks(self):
        gh = StableGH(self.key)
        previous = self.source
        count = [0]
        def changing_sources():
            count[0] += 1
            if count[0] == 1:
                return previous()
            return (self.canonical, (
                self.accounts[0].replace(
                    b"refresh-users_library_1", b"later-rotated"),
                self.accounts[1]))
        self.source = changing_sources
        self.assertEqual(self.run_sync(gh), "blocked_local_changed")
        self.assertIsNone(gh.blob)

    def test_branch_drift_before_put_blocks(self):
        gh = StableGH(self.key)
        count = [0]
        def drift():
            count[0] += 1
            return "a" * 40 if count[0] == 1 else "d" * 40
        gh.head = drift
        self.assertEqual(self.run_sync(gh), "blocked_repository_changed")

    def test_create_conflict_no_retry(self):
        gh = StableGH(self.key)
        gh.put_override = (422, {})
        self.assertEqual(self.run_sync(gh), "conflict_no_retry")
        self.assertEqual(gh.calls.count(("put", routes.V2_REMOTE_PATH)), 1)

    def test_update_conflict_no_retry(self):
        self.accounts = (
            self.accounts[0].replace(
                b"refresh-users_library_1", b"new-refresh"), self.accounts[1])
        gh = StableGH(self.key, self.canonical)
        gh.put_override = (409, {})
        self.assertEqual(self.run_sync(gh), "conflict_no_retry")
        self.assertEqual(gh.calls.count(("put", routes.V2_REMOTE_PATH)), 1)

    def test_status_200_for_create_is_not_success(self):
        gh = StableGH(self.key)
        gh.put_override = (200, {})
        self.assertEqual(self.run_sync(gh), "put_failed")

    def test_status_201_for_update_is_not_success(self):
        self.accounts = (
            self.accounts[0].replace(
                b"refresh-users_library_1", b"new-refresh"), self.accounts[1])
        gh = StableGH(self.key, self.canonical)
        gh.put_override = (201, {})
        self.assertEqual(self.run_sync(gh), "put_failed")

    def test_missing_put_confirmation_blocks(self):
        gh = StableGH(self.key)
        gh.put_override = (201, {"content": {"sha": "x"}})
        self.assertEqual(self.run_sync(gh), "put_unconfirmed")

    def test_readback_deleted_blocks(self):
        gh = StableGH(self.key)
        getter = gh.get
        count = [0]
        def vanishing(path):
            count[0] += 1
            if count[0] == 2:
                return 404, {"message": "Not Found"}
            return getter(path)
        gh.get = vanishing
        self.assertEqual(self.run_sync(gh),
                         "blocked_readback_remote_invalid")

    def test_post_put_drift_is_not_verified(self):
        gh = StableGH(self.key)
        orig_head = gh.head
        n = [0]
        def drift():
            n[0] += 1
            if n[0] == 3:
                return "d" * 40
            return orig_head()
        gh.head = drift
        self.assertEqual(self.run_sync(gh), "blocked_readback_branch_drift")

    def test_post_put_local_changed_is_not_verified(self):
        gh = StableGH(self.key)
        previous = self.source
        n = [0]
        def read():
            n[0] += 1
            if n[0] < 3:
                return previous()
            return self.canonical, (
                self.accounts[0].replace(
                    b"refresh-users_library_1", b"late"), self.accounts[1])
        self.source = read
        self.assertEqual(self.run_sync(gh),
                         "published_local_changed_requires_recheck")

    def test_google_drive_preserved_in_composition(self):
        rotated = self.accounts[1].replace(
            b"refresh-users_library_2", b"new-token")
        result = master.compose_current(
            self.canonical, (self.accounts[0], rotated))
        canon_opts = policy.sections(self.canonical)
        opts = policy.sections(result)
        for name in ("updater", "logs"):
            self.assertEqual(opts[name], canon_opts[name])

    def test_no_plaintext_gh_payload(self):
        gh = StableGH(self.key)
        payloads = []
        original_put = gh.put
        def log_put(path, payload):
            payloads.append(copy.deepcopy(payload))
            return original_put(path, payload)
        gh.put = log_put
        self.assertEqual(self.run_sync(gh), "created_verified")
        txt = str(payloads)
        self.assertNotIn("refresh-users_library", txt)
        self.assertNotIn("one_a", txt)
        self.assertNotIn("users_library_1", txt)

    def test_source_has_no_live_network_or_rclone(self):
        source = (Path(__file__).resolve().parents[1] /
                  "lib/rclone_two_mount_master_sync.py").read_text()
        for term in ("import subprocess", "import urllib", "import socket",
                     "systemctl", "os.replace(", "os.unlink("):
            with self.subTest(term=term):
                self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
