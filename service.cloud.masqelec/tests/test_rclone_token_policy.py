# -*- coding: utf-8 -*-
"""OAuth policy, no Kodi, network, or actual secrets."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_token_policy as policy


def conf(refresh, access="a", expiry="2026-11-17T09:00:00Z", chunk="64M"):
    value = json.dumps({
        "access_token": access,
        "refresh_token": refresh,
        "expiry": expiry,
    }, sort_keys=True)
    return ("[cloud]\ntype = drive\nclient_id = x\nchunk_size = {}\ntoken = {}\n"
            .format(chunk, value)).encode("utf-8")


def master_conf_with_extras():
    providers = ("onedrive", "onedrive", "drive", "drive")
    sections = []
    for n, provider in enumerate(providers, 1):
        token = json.dumps({
            "access_token": "access{}".format(n),
            "refresh_token": "refresh{}".format(n),
            "expiry": "2026-11-17T09:00:00Z",
        })
        section = ["[oauth{}]".format(n), "type = " + provider,
                   "client_id = app"]
        if provider == "onedrive":
            section.extend(["drive_id = od{}".format(n),
                            "drive_type = personal"])
        section.extend(["token = " + token, ""])
        sections.extend(section)
    sections.extend(["[alias]", "type = alias", "remote = oauth1:", "",
                     "[secure]", "type = crypt", "remote = oauth2:folder",
                     "password = sample-test", ""])
    return "\n".join(sections).encode("utf-8")


class RcloneTokenPolicyTests(unittest.TestCase):
    def test_ignore_access_and_expiry_churn(self):
        local = conf("valid", "access-two", "2026-11-17T12:00:00Z")
        old = conf("valid", "access-one", "2026-11-17T09:00:00Z")
        self.assertEqual(policy.stable_oauth_fingerprint(local),
                         policy.stable_oauth_fingerprint(old))
        self.assertFalse(policy.master_should_publish(local, old))

    def test_publish_rotated_refresh_when_newer(self):
        local = conf("rotated", "new", "2026-11-17T13:00:00Z")
        old = conf("older", "old", "2026-11-17T09:00:00Z")
        self.assertTrue(policy.master_should_publish(local, old))

    def test_access_expiry_does_not_rank_refresh_age(self):
        local = conf("older", expiry="2026-11-17T09:00:00Z")
        old = conf("rotated", expiry="2026-11-17T13:00:00Z")
        # La fecha de access_token no es la de emisión de refresh_token.
        # La validez se comprobará con rclone antes de publicar.
        self.assertTrue(policy.master_should_publish(local, old))

    def test_master_fences_non_token_changes(self):
        local = conf("same", chunk="128M")
        old = conf("same", chunk="64M")
        with self.assertRaisesRegex(ValueError, "opciones no OAuth"):
            policy.master_should_publish(local, old)

    def test_master_fences_static_change_even_if_refresh_rotated(self):
        local = conf("new", chunk="128M")
        old = conf("old", chunk="64M")
        with self.assertRaisesRegex(ValueError, "opciones no OAuth"):
            policy.master_should_publish(local, old)

    def test_master_rejects_identity_change(self):
        local = conf("same").replace(b"client_id = x", b"client_id = different")
        old = conf("same")
        with self.assertRaisesRegex(ValueError, "opciones no OAuth"):
            policy.master_should_publish(local, old)

    def test_client_only_changes_failed_token(self):
        local = conf("bad")
        remote = conf("good")
        combined = policy.tokens_from_master(local, remote, ["cloud"])
        self.assertIn(b'"refresh_token": "good"', combined)
        self.assertNotIn(b'"refresh_token": "bad"', combined)
        self.assertEqual(policy.sections(local)["cloud"]["chunk_size"],
                         policy.sections(combined)["cloud"]["chunk_size"])

    def test_client_requires_new_refresh(self):
        with self.assertRaisesRegex(ValueError, "diferente"):
            policy.tokens_from_master(conf("same", "old"),
                                      conf("same", "new"), ["cloud"])

    def test_client_rejects_wrong_identity(self):
        local = conf("bad")
        remote = conf("good").replace(b"client_id = x", b"client_id = other")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            policy.tokens_from_master(local, remote, ["cloud"])

    def test_auth_failure_not_network_or_quota(self):
        self.assertTrue(policy.auth_failure(b"failed to refresh token: invalid_grant"))
        self.assertTrue(policy.auth_failure(b"oauth2: cannot fetch token"))
        self.assertFalse(policy.auth_failure(b"Failed to list: timeout"))
        self.assertFalse(policy.auth_failure(b"rate limit exceeded"))
        self.assertFalse(policy.auth_failure(b"permission denied"))

    def test_malformed_tokens_fail_closed(self):
        bad = b'[cloud]\ntype = drive\ntoken = {not-json}\n'
        with self.assertRaisesRegex(ValueError, "JSON"):
            policy.oauth_tokens(bad)

    def test_onedrive_supported_but_box_not_shared(self):
        drive = conf("drive-token")
        onedrive = drive.replace(b"type = drive", b"type = onedrive")
        box = drive.replace(b"type = drive", b"type = box")
        self.assertEqual(list(policy.oauth_tokens(drive)), ["cloud"])
        self.assertEqual(list(policy.oauth_tokens(onedrive)), ["cloud"])
        self.assertEqual(policy.oauth_tokens(box), {})



    def test_four_remotes_two_of_each(self):
        parts = []
        for index, provider in enumerate(("onedrive", "onedrive", "drive", "drive"), 1):
            item = conf("refresh-{}".format(index))
            item = item.replace(b"[cloud]", ("[remote{}]".format(index)).encode())
            item = item.replace(b"type = drive", ("type = {}".format(provider)).encode())
            parts.append(item)
        mixed = b"\n".join(parts)
        self.assertEqual(len(policy.oauth_tokens(mixed)), 4)
        self.assertEqual(policy.oauth_provider_counts(mixed),
                         {"onedrive": 2, "drive": 2})
        changed = mixed.replace(b"refresh-2", b"refresh-other")
        self.assertEqual(policy.changed_refresh_names(changed, mixed), ("remote2",))
        self.assertTrue(policy.master_should_publish(changed, mixed))

    def test_only_access_renewed_onedrive_no_publish(self):
        local = conf("same-refresh", "new-access", "2026-11-20T12:00:00Z")
        old = conf("same-refresh", "old-access", "2026-11-19T09:00:00Z")
        local = local.replace(b"type = drive", b"type = onedrive")
        old = old.replace(b"type = drive", b"type = onedrive")
        self.assertFalse(policy.master_should_publish(local, old))

    def test_onedrive_drive_id_changed_blocks_recovery(self):
        local = conf("bad").replace(b"type = drive",
                                    b"type = onedrive\ndrive_id = id_A\ndrive_type = personal")
        published = conf("good").replace(b"type = drive",
                                        b"type = onedrive\ndrive_id = id_B\ndrive_type = personal")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            policy.tokens_from_master(local, published, ["cloud"])

    def test_onedrive_drive_type_changed_blocks_recovery(self):
        local = conf("bad").replace(b"type = drive",
                                    b"type = onedrive\ndrive_id = id_A\ndrive_type = personal")
        published = conf("good").replace(b"type = drive",
                                        b"type = onedrive\ndrive_id = id_A\ndrive_type = business")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            policy.tokens_from_master(local, published, ["cloud"])

    def test_onedrive_same_identity_recovers_without_static_modification(self):
        local = conf("bad", chunk="64M").replace(b"type = drive",
                          b"type = onedrive\ndrive_id = id_A\ndrive_type = personal")
        published = conf("good", chunk="32M").replace(b"type = drive",
                          b"type = onedrive\ndrive_id = id_A\ndrive_type = personal")
        candidate = policy.tokens_from_master(local, published, ["cloud"])
        self.assertEqual(policy.oauth_tokens(candidate)["cloud"]["refresh_token"], "good")
        self.assertEqual(policy.sections(candidate)["cloud"]["chunk_size"], "64M")

    def test_refresh_unchanged_despite_expiry_change_not_recovered(self):
        local = conf("same", "old-access")
        published = conf("same", "new-access")
        with self.assertRaisesRegex(ValueError, "diferente"):
            policy.tokens_from_master(local, published, ["cloud"])

    def test_onedrive_auth_error_vs_rate_limit(self):
        self.assertTrue(policy.auth_failure(b"OneDrive invalid_grant AADSTS700082"))
        self.assertTrue(policy.auth_failure(b"Graph invalidAuthenticationToken"))
        self.assertFalse(policy.auth_failure(b"Microsoft Graph 429 throttled"))
        self.assertFalse(policy.auth_failure(b"OneDrive 403 forbidden"))


    def test_master_inventory_requires_four_oauth_remotes(self):
        one = conf("one")
        with self.assertRaisesRegex(ValueError, "Inventario"):
            policy.validate_master_layout(one)

    def test_master_inventory_rejects_truncated_token_json(self):
        bad = (b'[a]\ntype = onedrive\ndrive_id = id_a\n'
               b'drive_type = personal\ntoken = {invalid\n')
        with self.assertRaisesRegex(ValueError, "JSON"):
            policy.validate_master_layout(bad)

    def test_master_partial_identity_rejects_wrong_onedrive_drive(self):
        published = (b'[a]\ntype = onedrive\ndrive_id = right\n'
                     b'drive_type = personal\ntoken = TOKEN\n')
        damaged = (b'[a]\ntype = onedrive\ndrive_id = wrong\n'
                   b'drive_type = personal\ntoken = {broken\n')
        self.assertFalse(policy.master_partial_identity_compatible(
            damaged, published))

    def test_master_partial_identity_allows_incomplete_json_if_drive_matches(self):
        published = (b'[a]\ntype = onedrive\ndrive_id = right\n'
                     b'drive_type = personal\ntoken = TOKEN\n')
        damaged = (b'[a]\ntype = onedrive\ndrive_id = right\n'
                   b'drive_type = personal\ntoken = {broken\n')
        self.assertTrue(policy.master_partial_identity_compatible(
            damaged, published))

    def test_master_can_restore_same_refresh_but_fixed_access_token(self):
        local = conf("shared", access="broken")
        remote = conf("shared", access="valid")
        candidate = policy.tokens_from_master(
            local, remote, ["cloud"], allow_same_refresh=True
        )
        self.assertIn(b'valid', candidate)
        with self.assertRaisesRegex(ValueError, "diferente"):
            policy.tokens_from_master(local, remote, ["cloud"])

    def test_master_does_not_copy_identical_token_even_in_failure(self):
        local = conf("shared", access="same")
        with self.assertRaisesRegex(ValueError, "alternativo"):
            policy.tokens_from_master(
                local, local, ["cloud"], allow_same_refresh=True
            )



    def test_master_allows_six_sections_with_four_oauth(self):
        raw = master_conf_with_extras()
        self.assertEqual(len(policy.sections(raw)), 6)
        self.assertEqual(policy.oauth_provider_counts(raw),
                         {"onedrive": 2, "drive": 2})
        self.assertEqual(policy.validate_master_layout(raw),
                         ("oauth1", "oauth2", "oauth3", "oauth4"))

    def test_master_rejects_extra_oauth_section_without_token(self):
        raw = master_conf_with_extras() + b"\n[broken]\ntype = onedrive\n"
        with self.assertRaisesRegex(ValueError, "Inventario"):
            policy.validate_master_layout(raw)

    def test_master_rejects_missing_oauth_token_among_six_sections(self):
        raw = master_conf_with_extras()
        lines = [line for line in raw.splitlines()
                 if b'"refresh_token": "refresh4"' not in line]
        with self.assertRaisesRegex(ValueError, "Inventario"):
            policy.validate_master_layout(b"\n".join(lines))

    def test_master_rejects_fifth_oauth_remote(self):
        raw = (master_conf_with_extras() +
               b'\n[fifth]\ntype = drive\ntoken = {"refresh_token":"extra"}\n')
        with self.assertRaisesRegex(ValueError, "Inventario"):
            policy.validate_master_layout(raw)

    def test_master_publishes_token_change_with_unchanged_extras(self):
        previous = master_conf_with_extras()
        refreshed = previous.replace(b"refresh1", b"new-refresh1")
        self.assertTrue(policy.master_should_publish(refreshed, previous))
        self.assertFalse(policy.master_should_publish(previous, previous))
        self.assertIn(b"[alias]", refreshed)
        self.assertIn(b"[secure]", refreshed)

    def test_master_does_not_publish_changed_non_oauth_settings(self):
        previous = master_conf_with_extras()
        modified = previous.replace(b"remote = oauth1:",
                                    b"remote = oauth2:")
        with self.assertRaisesRegex(ValueError, "opciones no OAuth"):
            policy.master_should_publish(modified, previous)

    def test_master_recovery_rejects_modified_extra_static_options(self):
        published = master_conf_with_extras()
        damaged = published.replace(b"remote = oauth1:",
                                    b"remote = unknown:")
        self.assertFalse(policy.master_partial_identity_compatible(
            damaged, published))

    def test_master_recovery_rejects_missing_non_oauth_section(self):
        published = master_conf_with_extras()
        damaged = published + b"\n[other]\ntype = alias\nremote = oauth3:\n"
        self.assertFalse(policy.master_partial_identity_compatible(
            damaged, published))


if __name__ == "__main__":
    unittest.main()
