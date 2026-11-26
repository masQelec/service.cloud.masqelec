# -*- coding: utf-8 -*-
"""Provision inicial de credenciales PVR."""

import os
import re
import tempfile

from pathlib import Path

from lib import pvr_playlist as playlist


class CredentialsError(RuntimeError):
    pass


def ensure_credentials(
    path=playlist.CREDENTIALS,
    *,
    get_net_info=None,
    copy_remote=None,
):

    path = Path(path)

    if os.path.lexists(path):

        # No sustituir credenciales existentes
        # silenciosamente si son invalidas.

        playlist.read_credentials(path)

        return "UNCHANGED"

    if get_net_info is None:
        from lib.utils import get_net_info

    if copy_remote is None:
        from lib.rclone_utils import (
            copy_remote_to_tmp_then_move
        )
        copy_remote = copy_remote_to_tmp_then_move

    info = get_net_info() or {}

    mac = str(
        info.get("eth0") or ""
    ).replace(":", "").lower()

    if not re.fullmatch(r"[0-9a-f]{12}", mac):

        raise CredentialsError(
            "DEVICE_MAC_UNAVAILABLE"
        )

    path.parent.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix=".pvr-credentials-",
        dir=path.parent,
    ) as temporary:

        stage = Path(temporary)

        if copy_remote(
            "masqelec",
            "masqelec/user/" + mac,
            str(stage),
        ) is not True:

            raise CredentialsError(
                "CREDENTIAL_PROVISION_FAILED"
            )

        source = stage / mac

        playlist.read_credentials(source)

        data = playlist.read_limited(
            source,
            playlist.MAX_CREDENTIALS,
        )

        candidate = stage / "validated"

        with candidate.open("xb") as stream:

            os.fchmod(stream.fileno(), 0o600)

            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

        # Publicacion exclusiva: no sobrescribir
        # unas credenciales creadas concurrentemente.

        try:

            os.link(candidate, path)

        except FileExistsError:

            playlist.read_credentials(path)

            return "UNCHANGED"

        directory = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY,
        )

        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    return "PROVISIONED"
