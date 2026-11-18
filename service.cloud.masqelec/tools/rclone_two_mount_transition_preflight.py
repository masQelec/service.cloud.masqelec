# -*- coding: utf-8 -*-
"""Diagnóstico REAL de transición de montajes: SOLO LECTURA, sin secretos.

Autocontenido para descarga por SSH a /tmp en KodiELEC. NO ejecuta
mount/umount/rclone lsf, OAuth, systemctl start/stop o escrituras a /storage.
No supone autorización de cutover por el resultado PASS_READ_ONLY.
"""
import configparser
import json
import os
import re
import shlex
import stat
import subprocess
import sys

CANONICAL = "/storage/.config/rclone/rclone.conf"
SYSTEMD = "/storage/.config/system.d"
STATE = "/storage/.config/masqelec/rclone-mount-mode.json"
SERVICES = (
    ("rclone_tvshows_1.service", 1, "tvshows", "/storage/.mnt/tvshows/1"),
    ("rclone_tvshows_2.service", 2, "tvshows", "/storage/.mnt/tvshows/2"),
    ("rclone_videos_1.service", 1, "movies", "/storage/.mnt/videos/1"),
    ("rclone_videos_2.service", 2, "movies", "/storage/.mnt/videos/2"),
)
NEW_UNITS = (
    "rclone_library_1.service", "rclone_library_2.service",
    "masqelec_bind_tvshows_1.service", "masqelec_bind_tvshows_2.service",
    "masqelec_bind_videos_1.service", "masqelec_bind_videos_2.service",
)
FUSE_NEW = ("/storage/.mnt/cloud/1", "/storage/.mnt/cloud/2")
FIELDS = ("CONFIG", "LEGACY_UNITS", "LEGACY_MOUNTS",
          "LEGACY_SERVICES", "NEW_MOUNTS_ABSENT",
          "NEW_UNITS_ABSENT", "ROLLOUT_STATE_LEGACY")


def _read_regular(path, limit=1024 * 1024, private=False):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("not a regular bounded source")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("config not private")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        start = os.fstat(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        end = os.fstat(fd)
        if (not stat.S_ISREG(start.st_mode) or
                start.st_dev != info.st_dev or start.st_ino != info.st_ino or
                start.st_size != end.st_size or
                start.st_mtime_ns != end.st_mtime_ns or
                len(raw) != start.st_size):
            raise ValueError("source changed")
        return raw
    finally:
        os.close(fd)


def _parse_conf(raw):
    cfg = configparser.RawConfigParser(interpolation=None, strict=True)
    cfg.read_string(raw.decode("utf-8", "strict"))
    return cfg


def valid_config(raw):
    """Solo valida estructura y presencia; nunca muestra tokens o nombres."""
    try:
        cfg = _parse_conf(raw)
        sections = cfg.sections()
        providers = [cfg.get(s, "type", fallback="").lower()
                     for s in sections]
        if providers.count("onedrive") != 2 or providers.count("drive") != 2:
            return False
        owners = set()
        for i in (1, 2):
            crypt = "users_library_{}".format(i)
            if not cfg.has_section(crypt) or cfg.get(
                    crypt, "type", fallback="").lower() != "crypt":
                return False
            if cfg.get(crypt, "filename_encryption", fallback="") != "off":
                return False
            dest = cfg.get(crypt, "remote", fallback="")
            if dest.count(":") != 1:
                return False
            underlying = dest.split(":", 1)[0]
            if (underlying in owners or not cfg.has_section(underlying) or
                    cfg.get(underlying, "type", fallback="").lower() != "onedrive"):
                return False
            owners.add(underlying)
            if not cfg.get(underlying, "drive_id", fallback=""):
                return False
            if not cfg.get(underlying, "drive_type", fallback=""):
                return False
            token = json.loads(cfg.get(underlying, "token"))
            if (not isinstance(token, dict) or
                    not isinstance(token.get("refresh_token"), str) or
                    not token["refresh_token"]):
                return False
        if owners != {s for s in sections
                      if cfg.get(s, "type", fallback="").lower() == "onedrive"}:
            return False
        return True
    except (configparser.Error, ValueError, UnicodeError, KeyError, TypeError):
        return False


def _unit_args(raw):
    text = re.sub(r"\\\r?\n\s*", " ", raw.decode("utf-8", "strict"))
    starts = [line.partition("=")[2].strip() for line in text.splitlines()
              if line.startswith("ExecStart=")]
    if len(starts) != 1:
        raise ValueError("invalid ExecStart inventory")
    return shlex.split(starts[0])


def valid_units(units):
    if set(units) != {s[0] for s in SERVICES}:
        return False
    try:
        for name, i, folder, target in SERVICES:
            args = _unit_args(units[name])
            if (len(args) < 7 or os.path.basename(args[0]) != "rclone" or
                    args[1:4] != ["mount",
                                   "users_library_{}:{}".format(i, folder),
                                   target] or "--read-only" not in args):
                return False
            configs = [args[j + 1] for j, x in enumerate(args[:-1])
                       if x == "--config"]
            configs += [x.partition("=")[2] for x in args
                        if x.startswith("--config=")]
            if configs != [CANONICAL]:
                return False
        return True
    except (ValueError, UnicodeError, IndexError):
        return False


def _mounts(raw):
    """Última entrada de cada path, detectando apilamientos en las críticas."""
    mounts, counts = {}, {}
    for line in raw.splitlines():
        left, sep, right = line.partition(" - ")
        a, b = left.split(), right.split()
        if not sep or len(a) < 5 or len(b) < 3:
            raise ValueError("invalid mountinfo")
        path = a[4].replace("\\040", " ")
        counts[path] = counts.get(path, 0) + 1
        mounts[path] = {"fstype": b[0], "source": b[1], "root": a[3]}
    return mounts, counts


def check_mounts(raw):
    try:
        mounts, counts = _mounts(raw)
        old = (all(counts.get(target) == 1 and
                   mounts[target]["fstype"] == "fuse.rclone"
                   for _, _, _, target in SERVICES))
        new_absent = all(path not in mounts for path in FUSE_NEW)
        return old, new_absent
    except (ValueError, TypeError, KeyError):
        return False, False


def evaluate(config, units, mountinfo, active, new_units_exist,
             state_absent=True):
    old, roots_clear = check_mounts(mountinfo)
    report = {
        "CONFIG": valid_config(config),
        "LEGACY_UNITS": valid_units(units),
        "LEGACY_MOUNTS": old,
        "LEGACY_SERVICES": all(active.get(name) is True
                               for name, _, _, _ in SERVICES),
        "NEW_MOUNTS_ABSENT": roots_clear,
        "NEW_UNITS_ABSENT": new_units_exist is False,
        "ROLLOUT_STATE_LEGACY": state_absent is True,
    }
    return report


def _active(unit):
    try:
        return subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=6, check=False,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--preflight"]:
        print("PREFLIGHT_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=TWO_FUSE_TRANSITION_READ_ONLY")
    print("ONEDRIVE_ACCESSED=NO")
    print("LIVE_CONFIG_WRITE=NO")
    print("RCLONE_TOKEN_VALUES_PRINTED=NO")
    print("MOUNT_OR_SYSTEMD_MUTATIONS=NO")
    print("PLAYBACK_IDLE=NOT_VERIFIED")
    print("CUTOVER_AUTHORIZED=NO")
    report = {field: False for field in FIELDS}
    try:
        config = _read_regular(CANONICAL, private=True)
        units = {name: _read_regular(os.path.join(SYSTEMD, name))
                 for name, _, _, _ in SERVICES}
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as stream:
            mounts = stream.read(4 * 1024 * 1024)
        active = {name: _active(name) for name, _, _, _ in SERVICES}
        report = evaluate(
            config, units, mounts, active,
            any(os.path.lexists(os.path.join(SYSTEMD, name))
                for name in NEW_UNITS),
            not os.path.lexists(STATE))
    except (OSError, ValueError, UnicodeError, configparser.Error):
        pass
    for field in FIELDS:
        print(field + "=" + ("PASS" if report[field] else "BLOCKED"))
    passed = all(report.values())
    print("PREFLIGHT_RESULT=" +
          ("PASS_READ_ONLY" if passed else "BLOCKED_LOCAL_PREREQUISITES"))
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
