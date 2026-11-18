# -*- coding: utf-8 -*-
"""Conciliación PURA para regresar de 2 FUSE a 4 montajes legacy.

No abre archivos, no guarda tokens, no invoca OAuth, rclone o systemctl.
Una activación futura debe detener ambos escritores v2 ANTES de leer los
snapshots, escribir de forma atómica una config privada y reiniciar legacy.
NUNCA hacer rollback usando sin más el rclone.conf previo al cutover.
"""
from lib import rclone_conf_merge as conf
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_plan as plan


def reconcile_canonical_for_rollback(baseline_raw, current_raw,
                                     account1_raw, account2_raw):
    """Combina solo dos tokens OneDrive desde snapshots de cada cuenta.

    La configuración canónica observada debe conservar exactamente los
    dos tokens OneDrive que tenía al cortar a v2. Si otro proceso los ha
    renovado, no se puede decidir prioridad: bloquear, no sobrescribir.
    Google Drive, comentarios, otras secciones y criptografía no se tocan.

    El resultado es SECRET-BEARING; el llamador no debe registrarlo.
    NO certifica que los refresh tokens sigan siendo aceptados por Microsoft.
    """
    policy.validate_master_layout(baseline_raw)
    policy.validate_master_layout(current_raw)
    if not conf.same_non_token_settings(baseline_raw, current_raw):
        raise ValueError("Cambio de configuración canónica no autorizado")

    baseline = policy.sections(baseline_raw)
    current = policy.sections(current_raw)
    if set(current) != set(baseline):
        raise ValueError("Inventario canónico incompatible")
    replacements = {}
    for index, isolated_raw in enumerate((account1_raw, account2_raw)):
        # La cadena autorizada sale del baseline, no del snapshot recibido.
        expected_raw = plan.account_snapshot(baseline_raw, index)
        expected = policy.sections(expected_raw)
        isolated = policy.sections(isolated_raw)
        oauth_name = next(
            name for name, fields in expected.items()
            if fields.get("type", "").lower() == "onedrive")
        if (set(expected) != set(isolated) or
                not conf.same_non_token_settings(expected_raw, isolated_raw)):
            raise ValueError("Identidad crypt/OneDrive alterada en snapshot")
        # Comparación TOTAL del token canónico: ante escritura concurrente
        # (aunque solo cambie access_token) no se elige uno arbitrariamente.
        if current[oauth_name].get("token") != baseline[oauth_name].get("token"):
            raise ValueError("Token canónico cambiado durante transición")
        tokens = policy.oauth_tokens(isolated_raw)
        if set(tokens) != {oauth_name}:
            raise ValueError("Token OneDrive aislado incompleto")
        replacements[oauth_name] = isolated[oauth_name]["token"]
    if len(replacements) != 2:
        raise ValueError("Se esperaban exactamente dos cuentas OneDrive")

    lines = conf._lines(current_raw)
    section = None
    replaced = set()
    result = []
    for line in lines:
        header = conf._SECTION.match(line)
        if header:
            section = header.group(1)
        option = conf._OPTION.match(line)
        if option and section in replacements and option.group(1).lower() == "token":
            # Mantener todo lo demás idéntico y no registrar el valor.
            line = line[:line.index("=") + 1] + " " + replacements[section]
            replaced.add(section)
        result.append(line)
    if replaced != set(replacements):
        raise ValueError("No se localizaron ambos tokens canónicos")
    output = ("\n".join(result).rstrip("\n") + "\n").encode("utf-8")
    policy.validate_master_layout(output)
    if not conf.same_non_token_settings(current_raw, output):
        raise ValueError("Cambio no-token no permitido")
    return output
