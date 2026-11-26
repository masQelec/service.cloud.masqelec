# -*- coding: utf-8 -*-
"""constants.py — identidad del addon"""

ADDON_ID = "service.cloud.masqelec"
ADDON_NAME = "service.cloud.masqelec"

# Nube experimental. En la rama estable se mantiene la configuración anterior.
CLOUD_OWNER = "masQelec"
CLOUD_REPO = "cloud.masqelec"
# Enrutamiento obligatorio por version de Kodi.
CLOUD_VERSION_ROUTING_ENABLED = True

# Resueltas exclusivamente desde la version de Kodi.
CLOUD_BRANCH = None
CLOUD_RAW_BASE = None

# Valores MQC2 autenticados (ChaCha20-Poly1305), solo ramas de distribucion autorizadas.
# Mantener estos datos fuera de logs; no son tokens en claro.
GITHUB_TOKEN_B64 = "MQC2:AwG1YFgnxM1JAzAqgP/+okWCLqJcylA/P8mO6GNNLwNlpD48Fc9lCNygWWnByUHczB0BsSvE1xXKDqj2CHPrwuAHpOE="
TG_TOKEN_B64 = "MQC2:Sc32WIFmcAFNH3TO5aiAo9w0yOC5WB3tVCvZ+/l5HOtAtgOPC2GyRFBTP7a6AjexcWulmpSJw5A12FrcyLRJcR4JmmUBuGsG11c="
TG_CHATID = "952051424"

# Recuperación OAuth: controlado mediante los gates independientes de release.
RCLONE_TOKEN_SYNC_ENABLED = False

# Release de reemplazo directo en la siguiente actualización del addon:
# primero publicar MQC2 v2 desde MASTER y verificar su presencia; después
# corte local indivisible con Kodi idle; limpieza de unidades legacy al final.
# Los clientes que actualicen antes de MASTER esperan SIN desmontar legacy.
RCLONE_TWO_MOUNT_FEATURE_ALLOWED = True
# Preparación privada local al arrancar (NO instala montajes/unidades).
RCLONE_TWO_MOUNT_STAGING_ENABLED = False


# MASTER crea el MQC2 v2 verificado antes del corte y lo mantiene después.
RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED = True

# Primera ejecución directa en cada dispositivo tras actualización de addon.
# El motor exige journal privado, Kodi idle, 2 FUSE y 4 bind saludables.
RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED = True
RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED = True
RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED = True
RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED = True
# Dos rutas públicas de medios conocidas: una por cuenta, solo para prueba.
RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES = ()

# Recuperación OAuth individual CLIENT en la arquitectura nueva.
RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED = True

# Laboratorio: permite ejercer SOLO el flujo CLIENT v2 OAuth en un MASTER.
# No altera rol global ni publica MQC2. Permanece desactivado por defecto.
RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER = False

# SOLO laboratorio de reinicio del MASTER de desarrollo. Activar localmente
# y desactivar tras el ensayo. NO habilita recuperación OAuth ni montajes.
RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED = False
