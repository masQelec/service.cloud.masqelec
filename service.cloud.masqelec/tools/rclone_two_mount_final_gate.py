# -*- coding: utf-8 -*-
"""Read-only consolidated v2 release diagnostic; no OAuth, mounts or writes.

Modes: --ubuntu-regression runs all unittest tests; --coreelec-readonly
inspects actual systemd unit ordering and release flags without modifying
units or credentials. A PASS of this script does NOT authorize deployment.
"""
import os
from pathlib import Path
import subprocess
import sys

ADDON = Path(__file__).resolve().parents[1]
TESTS = ADDON / "tests"
UNIT = "masqelec-v2-recovery.service"


def _run(command, *, timeout=90):
    try:
        return subprocess.run(command, cwd=str(ADDON),
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def regression():
    args = [sys.executable, "-m", "unittest", "discover",
            "-s", str(TESTS), "-p", "test_*.py", "-q"]
    p = _run(args, timeout=180)
    if p is None:
        return "BLOCKED_REGRESSION_UNAVAILABLE"
    output = (p.stderr + p.stdout).decode("utf-8", "replace")
    # Only print compact summary, never raw tracebacks (possibly sensitive).
    for line in output.splitlines():
        if line.startswith(("Ran ", "OK", "FAILED ")):
            print("TEST_SUMMARY=" + line)
    return "PASS_REGRESSION" if p.returncode == 0 and "Ran " in output and "\nOK" in output else "FAIL_REGRESSION"


def _properties(unit):
    p = _run(["systemctl", "show", unit, "--no-pager",
              "-p", "LoadState", "-p", "UnitFileState",
              "-p", "Wants", "-p", "After", "-p", "Before",
              "-p", "ExecStart"], timeout=12)
    if p is None or p.returncode:
        return None
    try:
        return dict(line.split("=", 1) for line in
                    p.stdout.decode("utf-8", "replace").splitlines()
                    if "=" in line)
    except ValueError:
        return None


def coreelec():
    kodi = _properties("kodi.service")
    recover = _properties(UNIT)
    print("CORE_ELEC_HOST_ROOT=" + ("YES" if os.geteuid() == 0 else "NO"))
    print("KODI_SYSTEMD_LOADED=" + (
        "YES" if kodi and kodi.get("LoadState") == "loaded" else "NO"))
    print("EARLY_BOOT_UNIT_LOADED=" + (
        "YES" if recover and recover.get("LoadState") == "loaded" else "NO"))
    wanted = bool(kodi and UNIT in kodi.get("Wants", "").split())
    ordered = bool(kodi and UNIT in kodi.get("After", "").split())
    before = bool(recover and "kodi.service" in recover.get("Before", "").split())
    exec_argument = bool(recover and "--recover" in recover.get("ExecStart", ""))
    print("KODI_WANTS_RECOVERY=" + ("YES" if wanted else "NO"))
    print("KODI_AFTER_RECOVERY=" + ("YES" if ordered else "NO"))
    print("RECOVERY_BEFORE_KODI=" + ("YES" if before else "NO"))
    print("RECOVERY_EXEC_RECOVER_ARG=" + ("YES" if exec_argument else "NO"))
    print("OAUTH_OR_CONFIG_READ=NO")
    print("SYSTEMD_MODIFICATIONS=NO")
    print("KODI_MOUNTS_MODIFIED=NO")
    if all((wanted, ordered, before, exec_argument)):
        return "PASS_INSTALLED_ORDERING_READONLY"
    return "BLOCKED_AUTOMATIC_BOOT_ORDER_NOT_VERIFIED"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ["--ubuntu-regression"]:
        result = regression()
    elif args == ["--coreelec-readonly"]:
        result = coreelec()
    else:
        result = "BLOCKED_INVALID_MODE"
    print("FINAL_GATE=" + result)
    print("PRODUCTION_RELEASE_AUTHORIZED=NO")
    return 0 if result.startswith("PASS_") else 2


if __name__ == "__main__":
    sys.exit(main())
