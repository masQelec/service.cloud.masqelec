# -*- coding: utf-8 -*-
"""Gate compuesto P0-B+P0-C, política PURA y estrictamente experimental.

Un resultado favorable nunca es permiso para refrescar, publicar MQC2,
sobrescribir una configuración ni reconfigurar montajes. No integra HTTP,
rclone, OAuth ni servicio Kodi.
"""
from lib import rclone_two_mount_fleet as fleet
from lib import rclone_two_mount_generation as generations


def evaluate_synthetic_fleet_gate(first, second, generation_window,
                                  current_inventory, registry_revision,
                                  now, canonical, accounts, remote,
                                  blob_sha, branch_head, epochs, *,
                                  registry_verified=False,
                                  fleet_complete=False,
                                  remote_authenticated=False):
    """Exige cohorte de ambos OneDrive y baseline coherente.

    No intenta recuperar un baseline divergente: ante diferencias del
    refresh, incluso con todas las confirmaciones, se requiere decisión
    humana y coordinación real. El estado positivo SOLO sirve en tests.
    """
    fleet_status = fleet.assess_canonical_pair(
        first, second, current_inventory, registry_revision, now,
        inventory_authoritative=registry_verified,
        fleet_complete=fleet_complete,
    )
    if fleet_status != "both_accounts_quiescent_lab_only":
        return fleet_status
    if not isinstance(generation_window, generations.GenerationWindow):
        return "blocked_generation_window_missing"
    if generation_window.baseline != "baseline_equal":
        return "blocked_published_baseline_diverged"
    change = generations.recheck_window(
        generation_window, canonical, accounts, remote, blob_sha,
        branch_head, epochs, remote_authenticated=remote_authenticated,
    )
    if change != "stable_for_lab_only":
        return change
    return "dual_fence_lab_only"
