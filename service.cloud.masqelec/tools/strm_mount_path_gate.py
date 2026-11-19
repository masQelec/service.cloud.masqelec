#!/usr/bin/env python3
"""Offline, read-only mount-path compatibility gate for two local STRM accounts.

Does not touch OAuth, rclone, FUSE, systemd or mounted media.
Usage: python3 tools/strm_mount_path_gate.py --manifest /private/path/manifest.json
Manifest keys: accounts (exactly two), each with id, old_mount,
new_mount, sample_strm (nonempty list of local .strm files).
Never prints media paths or STRM contents.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

MAX_STRM_BYTES = 16 * 1024


def absolute_mount(value):
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("MOUNT_NOT_ABSOLUTE")
    if value != os.path.normpath(value):
        raise ValueError("MOUNT_NOT_CANONICAL")
    if value == "/":
        raise ValueError("ROOT_MOUNT_DISALLOWED")
    return value


def strm_local_path(text):
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    if len(lines) != 1:
        raise ValueError("STRM_NOT_SINGLE_LINE")
    ref = lines[0]
    if ref.startswith("file://"):
        url = urlsplit(ref)
        if url.netloc not in ("", "localhost") or url.query or url.fragment:
            raise ValueError("UNSUPPORTED_FILE_URL")
        ref = unquote(url.path)
    if not ref.startswith("/") or os.path.normpath(ref) != ref:
        raise ValueError("NONLOCAL_OR_NONCANONICAL_STRM")
    return ref


def belongs_to_mount(path, mount):
    return path.startswith(mount + "/")


def inspect_manifest(manifest):
    accounts = manifest.get("accounts")
    if not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("EXACTLY_TWO_ACCOUNTS_REQUIRED")
    seen_ids, seen_mounts, seen_samples = set(), set(), set()
    result = []
    for account in accounts:
        account_id = account.get("id")
        if not isinstance(account_id, str) or not account_id or account_id in seen_ids:
            raise ValueError("ACCOUNT_ID_INVALID_OR_DUPLICATE")
        seen_ids.add(account_id)
        old = absolute_mount(account.get("old_mount"))
        new = absolute_mount(account.get("new_mount"))
        if old != new:
            raise ValueError("MOUNT_PATH_MISMATCH")
        if old in seen_mounts:
            raise ValueError("MOUNT_COLLISION")
        seen_mounts.add(old)
        sample_files = account.get("sample_strm")
        if not isinstance(sample_files, list) or not sample_files:
            raise ValueError("STRM_SAMPLES_MISSING")
        count = 0
        for sample in sample_files:
            if not isinstance(sample, str) or not sample.startswith("/") or not sample.endswith(".strm"):
                raise ValueError("SAMPLE_PATH_INVALID")
            if sample in seen_samples:
                raise ValueError("SAMPLE_REUSED_ACROSS_ACCOUNTS")
            seen_samples.add(sample)
            path = Path(sample)
            # No actual media path is opened. Only the local .strm text is read.
            with path.open("rb") as handle:
                raw = handle.read(MAX_STRM_BYTES + 1)
            if len(raw) > MAX_STRM_BYTES:
                raise ValueError("STRM_TOO_LARGE")
            ref = strm_local_path(raw.decode("utf-8-sig"))
            if not belongs_to_mount(ref, old):
                raise ValueError("STRM_MOUNT_PREFIX_MISMATCH")
            count += 1
        result.append((account_id, count))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Private local JSON manifest")
    args = parser.parse_args(argv)
    try:
        with open(args.manifest, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        result = inspect_manifest(manifest)
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        # Only error category, never paths or exception text.
        category = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("MOUNT_PATH_EQUIVALENCE=FAIL")
        print("FAIL_CATEGORY=" + category)
        print("CUTOVER_AUTHORIZED=NO")
        return 2
    print("LAB_MODE=LOCAL_STRM_PATH_EQUIVALENCE_READ_ONLY")
    print("ONEDRIVE_ACCESSED=NO")
    print("FUSE_OR_SYSTEMD_CHANGED=NO")
    print("OAUTH_CONFIG_READ=NO")
    print("STRM_FILES_CHANGED=NO")
    print("MEDIA_PATHS_PRINTED=NO")
    for index, (_account, count) in enumerate(result, 1):
        print("ACCOUNT_%d_STRM_SAMPLES_VALID=%d" % (index, count))
    print("MOUNT_PATH_EQUIVALENCE=PASS")
    print("REAL_OAUTH_PROBE_ALLOWED=NO")
    print("CUTOVER_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
