# -*- coding: utf-8 -*-
"""v2: OneDrive credentials live exclusively in per-account rclone files.

This module NEVER calls rclone or GitHub. A transient full view is used for
compatibility with existing authenticated MQC2 validation; it is not stored.
Only known OneDrive and their two crypt wrappers are removed from general.
"""
import os
import stat
import tempfile

from lib import rclone_conf_merge as conf
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_startup_stage as stage


def _is_root():
    return os.geteuid() == 0


def _blocks(raw):
    """Preserve complete original sections, including unknown options."""
    lines = conf._lines(raw)
    blocks, current = [], None
    prefix = []
    for line in lines:
        found = conf._SECTION.match(line)
        if found:
            current = found.group(1)
            blocks.append([current, [line]])
        elif current is None:
            prefix.append(line)
        else:
            blocks[-1][1].append(line)
    # Reuse strict duplicate/option parser; do not silently merge duplicates.
    conf._sections(lines)
    return prefix, blocks


def _encode(prefix, blocks):
    rows = list(prefix)
    for _, lines in blocks:
        rows.extend(lines)
    return ("\n".join(rows).rstrip("\n") + "\n").encode("utf-8")


def _identities(accounts):
    if type(accounts) not in (tuple, list) or len(accounts) != 2:
        raise ValueError("Two private OneDrive sources required")
    from lib import rclone_mount_isolation as isolation
    expected = {}
    for index, raw in enumerate(accounts):
        if type(raw) is not bytes:
            raise ValueError("Invalid isolated config")
        sections = policy.sections(raw)
        wrapper = plan.ACCOUNT_REMOTES[index]
        if wrapper not in sections or sections[wrapper].get("type", "").lower() != "crypt":
            raise ValueError("Wrong crypt wrapper")
        names = [name for name, opts in sections.items()
                 if opts.get("type", "").strip().lower() == "onedrive"]
        if len(names) != 1 or len(sections) != 2 or not sections[names[0]].get("token"):
            raise ValueError("Wrong isolated OneDrive inventory")
        dependency = isolation.dependency_closure(raw, wrapper)
        if len(dependency) != 2 or set(dependency) != set(sections):
            raise ValueError("Untrusted OneDrive dependency")
        for name in sections:
            if name in expected:
                raise ValueError("Overlapping OneDrive accounts")
            expected[name] = sections[name]
    return expected


def general_only(raw, accounts):
    """Remove only the exact isolated wrappers and OneDrive sections."""
    if type(raw) is not bytes or not 0 < len(raw) <= 1024 * 1024:
        raise ValueError("Invalid general config")
    isolated = _identities(accounts)
    prefix, blocks = _blocks(raw)
    present = policy.sections(raw)
    for name, opts in present.items():
        if name in isolated:
            if ({k: v for k, v in opts.items() if k != "token"} !=
                    {k: v for k, v in isolated[name].items() if k != "token"}):
                raise ValueError("Existing OneDrive identity mismatch")
        elif opts.get("type", "").strip().lower() == "onedrive":
            raise ValueError("Unexpected OneDrive section")
    reduced = _encode(prefix, [(name, lines) for name, lines in blocks
                               if name not in isolated])
    remaining = policy.sections(reduced)
    if any(name in remaining for name in isolated):
        raise ValueError("Isolated section left in general config")
    if sum(opts.get("type", "").strip().lower() == "drive"
           for opts in remaining.values()) != 2:
        raise ValueError("Expected two Google Drive remotes")
    for required in ("masqelec", "log"):
        if required not in remaining:
            raise ValueError("Required general remote absent")
    return reduced


def full_view(raw, accounts):
    """Validated virtual canonical with current tokens from each active FUSE."""
    general = general_only(raw, accounts)
    prefix, blocks = _blocks(general)
    combined = list(blocks)
    for account in accounts:
        _, parts = _blocks(account)
        combined.extend(parts)
    result = _encode(prefix, combined)
    policy.validate_master_layout(result)
    if len(result) > 1024 * 1024:
        raise ValueError("Virtual canonical too large")
    # Re-extract the canonical account identity, disallowing cross-account
    # tokens or malformed crypt dependencies.
    for index in (0, 1):
        if not conf.same_non_token_settings(
                plan.account_snapshot(result, index), accounts[index]):
            raise ValueError("Account identity mismatch")
    return result


def local_sources():
    """Stable private snapshots for existing MASTER and CLIENT MQC2 engines."""
    paths = (stage.LOCAL_CONF,) + plan.ACCOUNT_CONFS
    data = []
    for path in paths:
        raw, _ = stage._read_file(path, confidential=True)
        info = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode) or
                info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("Untrusted OAuth input")
        data.append(raw)
    accounts = tuple(data[1:])
    return full_view(data[0], accounts), accounts


def retire_once(*, authorized=False, conf_path=None, account_paths=None,
                health_verified=False):
    """Strip duplicates only in verified v2; preserve live isolated configs.

    No journal is deleted, and no process is restarted. Atomic replacement
    preserves 0600 and fsyncs. Unknown sections are never discarded.
    """
    if authorized is not True or health_verified is not True:
        return "BLOCKED_NOT_VERIFIED"
    if rollout.mode(True) != "active" or not _is_root():
        return "BLOCKED_NOT_ACTIVE"
    conf_path = stage.LOCAL_CONF if conf_path is None else conf_path
    account_paths = plan.ACCOUNT_CONFS if account_paths is None else account_paths
    if conf_path != stage.LOCAL_CONF or tuple(account_paths) != plan.ACCOUNT_CONFS:
        return "BLOCKED_UNEXPECTED_PATH"
    try:
        canonical, generation = stage._read_file(conf_path, confidential=True)
        info = os.lstat(conf_path)
        if (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
            return "BLOCKED_INPUT"
        accounts = []
        for path in account_paths:
            raw, _ = stage._read_file(path, confidential=True)
            meta = os.lstat(path)
            if (not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid != os.geteuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600):
                return "BLOCKED_INPUT"
            accounts.append(raw)
        accounts = tuple(accounts)
        # Full reconstruction validates the two isolated account credentials,
        # including the legacy canonical when still present.
        full_view(canonical, accounts)
        reduced = general_only(canonical, accounts)
        if reduced == canonical:
            return "ALREADY_CLEAN"
        folder = os.path.dirname(conf_path)
        if os.path.islink(folder):
            return "BLOCKED_INPUT"
        fd, tmp = tempfile.mkstemp(prefix=".rclone-general-", dir=folder)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(reduced)
                stream.flush()
            os.fsync(fd)
            current, current_generation = stage._read_file(
                conf_path, confidential=True)
            if current != canonical or current_generation != generation:
                return "BLOCKED_LOCAL_CHANGED"
            os.replace(tmp, conf_path)
            tmp = None
            parent_fd = os.open(folder, os.O_RDONLY |
                                getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            os.close(fd)
            if tmp is not None and os.path.lexists(tmp):
                os.unlink(tmp)
        return "CLEANED"
    except (OSError, ValueError, TypeError, UnicodeError):
        return "BLOCKED_INPUT"
