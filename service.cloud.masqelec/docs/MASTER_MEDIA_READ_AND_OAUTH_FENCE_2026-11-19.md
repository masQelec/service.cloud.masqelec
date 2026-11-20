# MASTER: siguiente gate de acceso multimedia y coordinación OAuth

Estado: **diseño seguro; no ejecuta cutover ni sondeos OAuth**.

## Evidencia existente (19-11-2026)

- Suite Ubuntu: 778/778 PASS (resultado aportado por operador).
- Inventario local STRM: dos muestras FOUND; no se imprime ninguna ruta.
- Preflight físico del MASTER: siete condiciones PASS_READ_ONLY, cuatro FUSE legacy activos y raíces nuevas ausentes.
- Los cuatro destinos Kodi que deben conservarse son `/storage/.mnt/videos/{1,2}` y `/storage/.mnt/tvshows/{1,2}`.

## Advertencia crítica: aislamiento de ficheros no equivale a aislamiento OAuth

Ejecutar `rclone lsf` o crear otros FUSE con la **misma cuenta OneDrive** puede renovar el refresh token incluso usando una copia privada del archivo de configuración. Esto puede invalidar tokens usados por los procesos actuales o por otros clientes. Por ello `tools/rclone_two_mount_real_probe_lab.py --real-probe` está deliberadamente bloqueado con montajes activos y sin coordinación de flota.

**No iniciar nuevos rclone contra las dos cuentas reales en paralelo con los legacy.**

## Fases pendientes

1. Lectura de una muestra por cuenta usando los **montajes legacy existentes**, sin escribir ficheros ni cambiar systemd. Esto acredita únicamente acceso actual, no arquitectura v2. Limitar la espera, proteger rutas y no imprimir datos multimedia; diseñar y probar un ejecutor que pueda cancelar limpiamente bloqueos FUSE antes de emplearlo en MASTER.
2. Comparar rutas del plan v2 con exactamente los cuatro destinos antiguos (gate offline existente en `test_rclone_two_mount_kodi_path_contract.py`).
3. Probar 2 FUSE + 4 bind sobre backend **LOCAL ficticio** en `/tmp` (laboratorio existente), sin credenciales.
4. Diseñar coordinación de refresh tokens entre MASTER y CLIENTES, más recuperación ante corte de energía y caída de montaje.
5. Solo tras superar lo anterior: ventana de prueba física controlada y reversible de v2, sin reproducción Kodi activa, con copias verificadas y rollback.

## Límites

```text
CUTOVER_AUTHORIZED=NO
REAL_OAUTH_PROBE_ALLOWED=NO
LEGACY_CLEANUP_AUTHORIZED=NO
STRM_FILES_CHANGED=NO
```

Ninguna prueba PASS offline sustituye la validación de acceso real y rollback.
