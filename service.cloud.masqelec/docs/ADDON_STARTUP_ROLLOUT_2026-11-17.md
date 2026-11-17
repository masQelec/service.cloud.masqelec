# Cloud masQelec — migración local al actualizar el addon (decisión de arquitectura)

**17-11-2026 · Rama addon/develop · Aclaración del operador integrada · NO DEPLOY.**

## Flujo real del producto

- El operador **MASTER** gestiona la biblioteca y su catálogo publicado. Los **CLIENTES** ya tienen instalado el addon y, según el operador, reciben actualizaciones; al arrancar tras una actualización ejecutan el código nuevo. **La distribución del paquete del addon no está implementada en `lib/updater.py`: ese módulo actualiza el sistema operativo.** El mecanismo externo de actualización del addon se toma como existente por información del operador, pero su integridad/distribución no se ha auditado aquí.
- MASTER y CLIENTES acceden al mismo contenido OneDrive con la autenticación existente. La biblioteca de películas/series llega mediante el **catálogo de rutas y archivos `.strm`**, no explorando directorios remotos en cada CLIENTE.
- El acceso a las rutas OneDrive a través de rclone se utiliza sobre todo para **reproducir** los archivos solicitados; no se debe introducir un `rclone lsf` ni un escaneo de carpetas por cliente como requisito de migración.
- `library_1`/ `library_2` son remotos OAuth OneDrive; `users_library_1`/ `users_library_2` son sus wrappers `crypt`. Se conservan contraseñas, opciones y `filename_encryption=off`.
- Las cuatro rutas de reproducción y de los `.strm` no pueden cambiar:
  `/storage/.mnt/videos/1`, `/storage/.mnt/videos/2`, `/storage/.mnt/tvshows/1`, `/storage/.mnt/tvshows/2`.

## Diseño final, en cada dispositivo por separado

```text
library_1 (OAuth) --> users_library_1 (crypt)
                         |
                         +--> rclone_library_1 (un FUSE /storage/.mnt/cloud/1)
                                   +-- bind movies  -> /storage/.mnt/videos/1
                                   +-- bind tvshows -> /storage/.mnt/tvshows/1

library_2 (OAuth) --> users_library_2 (crypt)
                         |
                         +--> rclone_library_2 (un FUSE /storage/.mnt/cloud/2)
                                   +-- bind movies  -> /storage/.mnt/videos/2
                                   +-- bind tvshows -> /storage/.mnt/tvshows/2
```

**2 procesos rclone + 4 bind mounts + 4 rutas Kodi idénticas**. Los bind son operaciones del kernel, no procesos rclone adicionales.

### Acciones del addon cuando arranca una versión actualizada

1. **LEGACY**: mientras los flags están apagados, no cambiar nada. Con versión final habilitada, validar el `rclone.conf` **local** (identidad OneDrive, `crypt`, tokens existentes) y generar dos snapshots privados `account1.conf` y `account2.conf` en una fase de preparación. No sustituir tokens con el MQC2 por su diferencia de fecha.
2. **PREPARED**: conservar cuatro montajes legacy mientras no se hayan superado comprobaciones locales de rclone/systemd, respaldo de unidades, reposo de reproducción y posibilidad real de rollback.
3. **ACTIVACIÓN FUTURA**: en una versión final expresamente habilitada, realizar una transición local y reversible, sin rediseñar el catálogo ni tocar rutas `.strm`; validar **2 FUSE + 4 bind** con `/proc/self/mountinfo`. No está implementado el ejecutor de cutover.
4. **ACTIVE**: comprobar los nuevos montajes al reiniciar el addon y no reactivar los cuatro legacy por una actualización posterior.
5. **FALLO/INSEGURO**: no sobrescribir credenciales ni reiniciar servicios a ciegas; conservar modo legacy o bloquear un estado parcial antes de empeorar la reproducción.

El addon ejecuta `start_cloud_storage()` al arrancar. Actualmente la rutina legacy descarga el MQC2, **preserva los tokens OAuth locales compatibles** (véase `rclone_conf_merge.preserve_local_oauth_tokens`) y puede actualizar las cuatro unidades legacy de `cloud/develop/system.d/` con `try-restart`; por eso, en la futura integración activa el modo v2 debe elegirse **antes** de actualizar servicios legacy. **No modificar `cloud/develop/system.d/` para pilotar la nueva arquitectura.**

La función pura `rclone_two_mount_rollout.startup_decision()` (commit `003d7816`) modela este comportamiento sin tocar servicios, y distingue `continue_legacy`, `stage_two_accounts_locally`, `keep_legacy_*`, `defer_migration_playback_active`, `plan_local_two_fuse_four_bind_cutover` y `verify_existing_two_fuse_four_bind`. Sus booleanos de readiness aún **no están cableados a comprobaciones operativas**: no es un activador. Las 15 nuevas pruebas se incluyen en la suite CI **352/352 OK** (run [44197364926](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44197364926)).

## OAuth sin sobreingeniería

- El MASTER mantiene el backup MQC2 de seis secciones para compatibilidad; la divergencia actual de OneDrive es conocida, producida por renovaciones rclone locales posteriores al backup.
- Microsoft no invalida automáticamente los `refresh_token` anteriores en cada renovación. No se ha probado el estado de cada sesión CLIENTE y no se debe sobrescribir su configuración válida.
- **La migración de 4 a 2 procesos por dispositivo NO requiere un coordinador central de flota**, siempre que no intente arbitrar ni promover tokens entre dispositivos. Cada CLIENTE preserva las credenciales locales al actualizar.
- La sincronización/recuperación futura de tokens entre dispositivos es un problema distinto; quedan desactivadas las funciones de publicación automática. Los prototipos P0-B/C de coordinación quedan como pruebas aisladas, **no como dependencia técnica de desplegar el diseño local 2 FUSE + 4 bind**.
- No existe autorización para cortar los montajes reales hasta ensayar en rutas alternativas el montaje FUSE, el bind, la reproducción de un archivo y el rollback. Nada de esto se considera pasado por las 352 pruebas sintéticas.

## Estados operativos

```text
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TOKEN_SYNC_ENABLED=False
ADDON_STARTUP_DECISION=LAB_ONLY
CUTOVER_EXECUTOR=NOT_IMPLEMENTED
KODI_2FUSE_4BIND_REAL=NOT_RUN
MQC2_OAUTH_PUBLISH=NO
LIVE_MOUNTS_CHANGED=NO
```

## Próximo trabajo concreto

Implementar el **staging local idempotente** invocado en el futuro arranque del addon usando `rclone_two_mount_plan.generate`, validar dependencias y permisos sin modificar `system.d`, y después preparar un piloto de FUSE/bind en rutas que no interfieran con los cuatro montajes activos. Solo entonces desarrollar el ejecutor de transición y reversión por dispositivo. No crear servidor, coordinador de flota, ni rediseñar el catálogo para este objetivo.
