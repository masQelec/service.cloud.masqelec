#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laboratorio integral con ZIP reales.

No ejecuta binarios ARM.
No utiliza Kodi ni systemd reales.
No modifica /storage ni publica paquetes.
"""

import os
import sys
import tempfile

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from lib import tvheadend_backup as backup
from lib import tvheadend_kodi as kodi
from lib import tvheadend_manifest as manifest
from lib import tvheadend_package as package
from lib import tvheadend_release_control as releases
from lib import tvheadend_platform as platform
from lib import tvheadend_staging as staging
from lib import tvheadend_transaction as tx
from lib import tvheadend_updater as updater
from lib import tvheadend_update_service as service
from lib import tvheadend_version as version


ROOT = Path(__file__).resolve().parents[1]

BUILD = Path.home() / "GitHub/KodiELEC"

MANIFEST = (
    ROOT / "docs/"
    "PVR_03_TVHEADEND_MANIFEST_CANDIDATE.json"
)

BRANCH = "21"

BASE = (
    "https://raw.githubusercontent.com/"
    "masQelec/cloud.masqelec/21"
)

GRABBER = b"#!/bin/sh\n# masQelec LAB ONLY\n"

OLD_VERSION = "21.2.7"
NEW_VERSION = "21.2.8"

OLD_NG_SIZE = 32654231

OLD_NG_SHA256 = (
    "a4c6d8b5bcaa1b62502c900fa5603d7d6"
    "ab77383708656d7ed15abd2c3079b2f"
)

EXPECTED_BINARIES = {
    "Amlogic-ng.arm": (
        "6c87ff5c3de2023373b9e36571f5de984"
        "8c074cddaafb995bfbd00089712cc80"
    ),
    "Amlogic-ne.aarch64": (
        "cf6db2cd3709384b861bb8b6f5f39f2c"
        "21881a7817be4ce4a4ccf1ba8a340d38"
    ),
}


def require(condition, code):

    if not condition:
        raise RuntimeError(code)


def zip_path(target, release):

    device, architecture = target.split(".", 1)

    return (
        BUILD
        / "target/addons"
        / device
        / "21.2"
        / architecture
        / tx.ADDON_ID
        / f"{tx.ADDON_ID}-{release}.zip"
    )


def lab_platform(target):

    device = target.split(".", 1)[0]

    return platform.detect_from_text(
        "\n".join((
            "ID=coreelec",
            "VERSION_ID=21.2.5",
            "VERSION=21.2.5-PVR03I2-LAB",
            f"COREELEC_ARCH={target}",
            f"LIBREELEC_ARCH={target}",
            f"COREELEC_DEVICE={device}",
        ))
    )


class LabKodi:

    def __init__(self, active, config):

        self.active = active
        self.config = config

        self.version = OLD_VERSION
        self.enabled = True

        self.calls = []

    def state(self):

        return kodi.AddonState(
            self.version,
            self.enabled,
        )

    def set_enabled(self, enabled, expected_version):

        require(
            self.version == expected_version,
            "LAB_KODI_VERSION_MISMATCH",
        )

        self.enabled = enabled

        self.calls.append((
            "enabled",
            enabled,
            expected_version,
        ))

        if enabled and self.version == NEW_VERSION:

            # Simular una escritura de configuracion
            # efectuada por la nueva version.

            (
                self.config / "config"
            ).write_text("modified by new version")

        return self.state()

    def rescan_disabled(self, expected_version):

        require(
            not self.enabled,
            "LAB_RESCAN_WHILE_ENABLED",
        )

        identity = tx.identity(self.active)

        require(
            identity["version"] == expected_version,
            "LAB_RESCAN_VERSION_MISMATCH",
        )

        self.version = expected_version

        self.calls.append((
            "rescan",
            expected_version,
        ))

        return self.state()


def synthetic_old_addon(active):

    active.mkdir()

    binary_dir = active / "bin"

    binary_dir.mkdir()

    (active / "addon.xml").write_text(
        f'<addon id="{tx.ADDON_ID}" '
        f'version="{OLD_VERSION}"/>'
    )

    binary = binary_dir / "tvheadend"

    binary.write_bytes(
        b"synthetic previous NE binary"
    )

    binary.chmod(0o755)

    grabber = binary_dir / "tv_grab_file"

    grabber.write_bytes(GRABBER)
    grabber.chmod(0o755)


def prepare_old_addon(
    base,
    active,
    device,
    entry,
):

    if device.target != "Amlogic-ng.arm":

        synthetic_old_addon(active)

        return "SYNTHETIC_NE"

    old_zip = zip_path(
        device.target,
        OLD_VERSION,
    )

    require(
        old_zip.is_file(),
        "OLD_NG_ZIP_MISSING",
    )

    old_entry = replace(
        entry,
        version=OLD_VERSION,
        path=(
            f"pvr/tvheadend/{device.target}/"
            f"{tx.ADDON_ID}-{OLD_VERSION}.zip"
        ),
        size=OLD_NG_SIZE,
        sha256=OLD_NG_SHA256,
    )

    old_root = base / "old-staging"

    old_root.mkdir(mode=0o700)

    fixture = base / "custom-grabber"

    fixture.write_bytes(GRABBER)

    staging.prepare_candidate(
        old_zip,
        old_entry,
        device,
        old_root,
        fixture,
    )

    os.rename(
        old_root / "candidate",
        active,
    )

    old_root.rmdir()

    return "REAL_NG_21.2.7"


def authorized_lab_manifest(
    distribution,
    device,
    entry,
):

    # La autorizacion solo existe en memoria.
    # No modifica el manifiesto candidato en disco.

    lab_entry = replace(
        entry,
        validated_builds=((
            device.coreelec_version,
            device.coreelec_build,
        ),),
    )

    return replace(
        distribution,
        packages=(lab_entry,),
    )


def run_case(
    distribution,
    entry,
    fail_health,
):

    target = entry.target

    device = lab_platform(target)

    new_zip = zip_path(
        target,
        NEW_VERSION,
    )

    require(
        new_zip.is_file(),
        "REAL_PACKAGE_MISSING",
    )

    # Comprobar que el manifiesto original no
    # autoriza instalaciones de laboratorio.

    try:

        manifest.select_package(
            distribution,
            device,
        )

    except Exception as error:

        require(
            str(error)
            == "COREELEC_BUILD_NOT_VALIDATED",
            "UNEXPECTED_MANIFEST_REJECTION",
        )

    else:

        raise RuntimeError(
            "UNVALIDATED_BUILD_AUTHORIZED"
        )

    lab_distribution = authorized_lab_manifest(
        distribution,
        device,
        entry,
    )

    with tempfile.TemporaryDirectory(
        prefix=".tvh-real-lab-",
        dir=Path.home(),
    ) as temporary:

        base = Path(temporary).resolve()

        addons = base / "addons"
        userdata = base / "addon_data"

        addons.mkdir()
        userdata.mkdir()

        active = addons / tx.ADDON_ID
        config = userdata / tx.ADDON_ID

        transaction_root = base / "transaction"

        config.mkdir()

        (config / "config").write_text(
            "original configuration"
        )

        (config / "channel").mkdir()

        (
            config / "channel/uuid-original"
        ).write_text('{"number":1}')

        old_config = backup.inventory(config)[1]

        previous = prepare_old_addon(
            base,
            active,
            device,
            entry,
        )

        old_identity = tx.identity(active)
        old_tree = backup.inventory(active)[1]

        controller = LabKodi(
            active, config
        )

        events = []

        def simulated_health(digest):

            require(
                controller.enabled,
                "LAB_SERVICE_DISABLED",
            )

            observed = tx.identity(active)

            require(
                observed["binary_sha256"] == digest,
                "LAB_BINARY_IDENTITY_MISMATCH",
            )

            if (
                fail_health
                and observed["version"] == NEW_VERSION
            ):

                return {"health": "FAILED"}

            return {"health": "PASS"}

        @contextmanager
        def local_stage(
            distribution_arg,
            device_arg,
            installed_version,
            branch,
            raw_base,
            staging_parent,
        ):

            require(
                branch == BRANCH
                and raw_base == BASE,
                "LAB_ROUTE_MISMATCH",
            )

            decision = version.decide_update(
                distribution_arg,
                device_arg,
                installed_version,
            )

            require(
                decision.status == "UPDATE_AVAILABLE",
                "LAB_UPDATE_NOT_AVAILABLE",
            )

            # ZIP real local, sin descarga HTTP.

            package.validate_zip(
                new_zip,
                decision.package,
                device_arg,
            )

            yield decision, new_zip

        worker = updater.TvheadendUpdater(
            active,
            config,
            transaction_root,
            controller,
            lambda: not controller.enabled,
            simulated_health,
            lambda: True,
            lambda: True,
            notify=events.append,
            wait=lambda seconds: None,
        )

        result = service.run_cycle(
            worker,
            branch=BRANCH,
            base=BASE,
            authorized=True,
            detect_device=lambda: device,
            fetch_manifest=lambda *args: lab_distribution,
            stage_package=local_stage,
            verify_protection=lambda: True,
            verify_policy=lambda: True,
            release_control=releases.ReleaseControl(
                transaction_root
            ),
        )

        expected_result = (
            "ROLLED_BACK"
            if fail_health
            else "UPDATED"
        )

        require(
            result == expected_result,
            "LAB_UNEXPECTED_UPDATE_RESULT",
        )

        require(
            not transaction_root.exists(),
            "LAB_TRANSACTION_NOT_ARCHIVED",
        )

        history = (
            base / "transaction-history"
        )

        archives = list(history.iterdir())

        require(
            len(archives) == 1,
            "LAB_ARCHIVE_COUNT_MISMATCH",
        )

        archived = archives[0]

        saved = backup.verify_backup(
            archived / "config-backup"
        )

        require(
            saved == old_config,
            "LAB_BACKUP_MISMATCH",
        )

        require(
            (
                active / "bin/tv_grab_file"
            ).read_bytes() == GRABBER,
            "LAB_CUSTOM_GRABBER_CHANGED",
        )

        require(
            (
                config / "channel/uuid-original"
            ).is_file(),
            "LAB_CHANNEL_IDENTITY_LOST",
        )

        if fail_health:

            require(
                tx.identity(active) == old_identity,
                "LAB_OLD_ADDON_NOT_RESTORED",
            )

            require(
                backup.inventory(active)[1] == old_tree,
                "LAB_OLD_TREE_NOT_RESTORED",
            )

            require(
                backup.inventory(config)[1] == old_config,
                "LAB_CONFIG_NOT_RESTORED",
            )

            failed_binary = tx.identity(
                archived / "candidate"
            )

            require(
                failed_binary["binary_sha256"]
                == EXPECTED_BINARIES[target],
                "LAB_FAILED_BINARY_MISMATCH",
            )

        else:

            current = tx.identity(active)

            require(
                current["version"] == NEW_VERSION
                and current["binary_sha256"]
                == EXPECTED_BINARIES[target],
                "LAB_NEW_BINARY_MISMATCH",
            )

            require(
                tx.identity(
                    archived / "candidate"
                ) == old_identity,
                "LAB_PREVIOUS_ADDON_LOST",
            )

        require(
            controller.enabled,
            "LAB_FINAL_SERVICE_DISABLED",
        )

        print("--------------------------------")
        print(f"TARGET={target}")
        print(f"PREVIOUS_PACKAGE={previous}")
        print("UNVALIDATED_BUILD_REJECTED=PASS")
        print("REAL_ZIP_VALIDATION=PASS")
        print(f"SCENARIO={expected_result}")
        print(f"RESULT={result}")
        print("BACKUP_INTEGRITY=PASS")
        print("CUSTOM_GRABBER=PASS")
        print("CHANNEL_FIXTURE_PRESERVED=PASS")
        print("TRANSACTION_ARCHIVED=PASS")

        if fail_health:

            print("OLD_ADDON_RESTORED=PASS")
            print("OLD_TREE_RESTORED=PASS")
            print("CONFIG_RESTORED=PASS")

            repeated = service.run_cycle(
                worker,
                branch=BRANCH,
                base=BASE,
                authorized=True,
                detect_device=lambda: device,
                fetch_manifest=lambda *args: lab_distribution,
                stage_package=local_stage,
                verify_protection=lambda: True,
                verify_policy=lambda: True,
                release_control=releases.ReleaseControl(
                    transaction_root
                ),
            )

            require(
                repeated == "FAILED_PACKAGE_BLOCKED",
                "FAILED_PACKAGE_RETRY_NOT_BLOCKED",
            )

            print("FAILED_PACKAGE_RETRY_BLOCKED=PASS")

        else:

            print("NEW_BINARY_IDENTITY=PASS")
            print("PREVIOUS_ADDON_PRESERVED=PASS")

        print("HEALTH_INTERFACE=SIMULATED")
        print("KODI_INTERFACE=SIMULATED")
        print("SYSTEMD_INTERFACE=SIMULATED")
        print("CASE=PASS")

    require(
        not base.exists(),
        "LAB_TEMPORARY_CLEANUP_FAILED",
    )

    print("LAB_CLEANUP=PASS")


def main():

    release = Path(
        "/etc/os-release"
    ).read_text()

    require(
        any(
            line.strip() in (
                "ID=ubuntu",
                'ID="ubuntu"',
            )
            for line in release.splitlines()
        ),
        "LAB_PLATFORM_REJECTED",
    )

    original_manifest = MANIFEST.read_bytes()

    distribution = manifest.parse_manifest(
        original_manifest,
        21,
    )

    require(
        {
            entry.target
            for entry in distribution.packages
        } == set(EXPECTED_BINARIES),
        "LAB_TARGET_SET_MISMATCH",
    )

    cases = 0

    for entry in distribution.packages:

        require(
            entry.version == NEW_VERSION,
            "LAB_PACKAGE_VERSION_MISMATCH",
        )

        require(
            not entry.validated_builds,
            "LAB_MANIFEST_ALREADY_AUTHORIZED",
        )

        for fail_health in (False, True):

            run_case(
                distribution,
                entry,
                fail_health,
            )

            cases += 1

    require(
        cases == 4,
        "LAB_CASE_COUNT_MISMATCH",
    )

    require(
        MANIFEST.read_bytes() == original_manifest,
        "LAB_MANIFEST_MODIFIED",
    )

    print("================================")
    print(f"REAL_PACKAGE_CASES={cases}")
    print("MANIFEST_UNCHANGED=PASS")
    print("ARM_BINARIES_EXECUTED=NO")
    print("MASTER_MODIFIED=NO")
    print("PRODUCTION_INSTALL_AUTHORIZED=NO")
    print("PVR_03I2A_FINAL=PASS")


if __name__ == "__main__":
    main()
