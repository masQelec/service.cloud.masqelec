#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from lib import tvheadend_boot as boot


def main():

    if sys.argv[1:] != ["--recover"]:

        print("TVH_EARLY_BOOT=INVALID_MODE")

        return 1

    if os.geteuid() != 0:

        print("TVH_EARLY_BOOT=BLOCKED_NOT_ROOT")

        return 1

    try:

        release = Path(
            "/etc/os-release"
        ).read_text()

        if not any(
            line.strip() in (
                "ID=coreelec",
                'ID="coreelec"',
            )
            for line in release.splitlines()
        ):

            print("TVH_EARLY_BOOT=BLOCKED_PLATFORM")

            return 1

        result = boot.recover_pending()

        print(
            f"TVH_EARLY_BOOT={result}"
        )

        # La politica es secundaria respecto a la
        # recuperacion. Si falla, no bloquear TVH.
        try:

            from lib import tvheadend_boot_policy

            result = tvheadend_boot_policy.activate_at_boot()

            print(f"TVH_UPDATE_POLICY={result}")

        except Exception as policy_error:

            print("TVH_UPDATE_POLICY=BLOCKED")
            print(
                "POLICY_ERROR_TYPE="
                + type(policy_error).__name__
            )

        return 0

    except Exception as error:

        print(
            "TVH_EARLY_BOOT=RECOVERY_FAILED"
        )

        print(
            f"ERROR_TYPE={type(error).__name__}"
        )

        if isinstance(
            error, boot.BootRecoveryError
        ):
            print(f"ERROR_CODE={error}")

        return 1


if __name__ == "__main__":
    sys.exit(main())
