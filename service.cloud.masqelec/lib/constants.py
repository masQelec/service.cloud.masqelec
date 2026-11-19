# -*- coding: utf-8 -*-
"""constants.py — identidad del addon"""

ADDON_ID = "service.cloud.masqelec"
ADDON_NAME = "service.cloud.masqelec"

# Nube experimental. En la rama estable se mantiene la configuración anterior.
CLOUD_OWNER = "masQelec"
CLOUD_REPO = "cloud.masqelec"
CLOUD_BRANCH = "develop"
CLOUD_RAW_BASE = (
    f"https://raw.githubusercontent.com/{CLOUD_OWNER}/{CLOUD_REPO}/{CLOUD_BRANCH}"
)

# Valores MQC2 autenticados (ChaCha20-Poly1305), solo rama develop.
# Mantener estos datos fuera de logs; no son tokens en claro.
GITHUB_TOKEN_B64 = "MQC2:AwG1YFgnxM1JAzAqgP/+okWCLqJcylA/P8mO6GNNLwNlpD48Fc9lCNygWWnByUHczB0BsSvE1xXKDqj2CHPrwuAHpOE="
TG_TOKEN_B64 = "MQC2:Sc32WIFmcAFNH3TO5aiAo9w0yOC5WB3tVCvZ+/l5HOtAtgOPC2GyRFBTP7a6AjexcWulmpSJw5A12FrcyLRJcR4JmmUBuGsG11c="
TG_CHATID = "952051424"

# Recuperación OAuth: preparado en develop, inicialmente inactivo hasta validación real.
RCLONE_TOKEN_SYNC_ENABLED = False

# La arquitectura dos FUSE/cuatro bind exige activación EXPLÍCITA por
# dispositivo y un coordinador OAuth v2. Mantener False en develop.
# Con False, un CLIENTE ya activo en v2 es bloqueado para evitar
# reactivar accidentalmente los cuatro servicios legacy.
RCLONE_TWO_MOUNT_FEATURE_ALLOWED = False
# Preparación privada local al arrancar (NO instala montajes/unidades).
RCLONE_TWO_MOUNT_STAGING_ENABLED = False


# Publicación automática MASTER del MQC2 v2 (requiere gates físicos de release).
RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED = False

# Activación automática en el primer arranque tras actualizar el addon.
# Desactivado hasta validación física de corte/reboot y rollback en KodiELEC.
RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED = False
RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED = False
RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED = False
RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED = False
# Dos rutas públicas de medios conocidas: una por cuenta, solo para prueba.
RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES = ()

# CLIENT v2 OAuth transactional installer. NEVER enable without physical gates.
RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED = False

# Laboratorio: permite ejercer SOLO el flujo CLIENT v2 OAuth en un MASTER.
# No altera rol global ni publica MQC2. Permanece desactivado por defecto.
RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER = False
