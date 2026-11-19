# -*- coding: utf-8 -*-
"""Persistent CoreELEC systemd unit directory, without touching existing modes.

Legacy devices may already have a group-writable system.d. This routine
does not silently chmod those installations; the v2 migration has its own
stricter read-only safety gate.
"""
import os
import stat


def ensure_directory(path):
    """Create missing system.d with 0755 even under umask 0002.

    Existing directories remain unchanged. Refuse symlinks and non-directory
    targets to avoid silently redirecting persistent unit writes.
    """
    path = os.path.normpath(path)
    if os.path.lexists(path):
        if not stat.S_ISDIR(os.lstat(path).st_mode):
            raise ValueError("systemd unit directory is not a real directory")
        return False

    # Caller supplies the trusted constant under /storage/.config.
    os.mkdir(path, 0o755)
    os.chmod(path, 0o755)
    return True
