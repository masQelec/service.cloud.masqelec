# -*- coding: utf-8 -*-
"""Scoped CLIENT OAuth v2 role selection, NEVER a global device-role override."""
from lib import constants


def allowed(real_role):
    if real_role == "CLIENT":
        return True
    return (real_role == "MASTER" and
            getattr(constants, "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
                    False) is True)


def label(real_role):
    if real_role == "CLIENT":
        return "CLIENT"
    if allowed(real_role):
        return "DEV_MASTER_AS_CLIENT_OAUTH_ONLY"
    return "BLOCKED"
