# Handoff — cutover automático 2 FUSE + 4 bind (19/11/2026)

**Repositorio:** masQelec/service.cloud.masqelec · rama `develop`.
**MASTER:** KodiELEC / CoreELEC, servicio `kodi.service`;
`/storage/.config/system.d` root:root 0755; `/storage` ext4.
El operador confirmó `MASTER_READINESS=PASS_READ_ONLY`, salida 0.
Regresión confirmada *antes* de esta implementación: **811/811 PASS**.
No atribuir PASS a la nueva suite sin ejecutar el comando.

## Decisión del usuario

La nueva versión del addon debe sustituir automáticamente los 4 FUSE
legacy por 2 FUSE + 4 bind cuando Kodi esté inactivo. Debe instalar los
servicios nuevos y retirar las unidades legacy tras comprobar los seis
montajes; si ya está activo el diseño v2, verificarlo y arrancar
únicamente unidades ausentes. La disponibilidad de OneDrive no es crítica:
un journal corrupto, token vencido o rollback imposible NO debe impedir
que arranquen KodiELEC, Kodi, Tvheadend, Docker, red y demás servicios.
Las rutas públicas Kodi **nunca cambian** y los .strm internos se preservan.

## Código en develop

- `lib/rclone_two_mount_autostart.py` conectado desde `service.py`:
  flags primero; estado legacy: archivos multimedia de prueba, instalación
  comprobada del recovery de boot, cutover con journal/rollback, eliminación
  legacy solo tras ACTIVE sano. Estado v2 activo: mantenimiento idempotente,
  independientemente de las muestras locales, y limpieza solo cuando hay
  verificación de los vídeos de prueba.
- `lib/rclone_two_mount_active_maintenance.py`: v2 activo no reinicia
  unidades sanas, arranca las ausentes y rechaza legacy activo, bind
  huérfano, raíz ocupada, origen active/unmounted, journal incompatible.
  No toca credenciales ni .strm.
- `lib/rclone_two_mount_boot_install.py`: instala en `system.d`
  `masqelec-v2-recovery.service` y
  `kodi.service.d/50-masqelec-v2-recovery.conf`, idempotente y sin
  pisar instalaciones de operador; valida `Wants` + `After` con
  `systemctl show kodi.service` tras `daemon-reload`. Se instala
  **antes de parar legacy**, y cualquier fallo impide el corte.
- `tools/rclone_two_mount_early_boot_run.py`: recupera si feature y
  rollback gates permiten, sin bloquear arranque, retorno siempre 0;
  errores inesperados no imprimen secretos.
- `lib/rclone_two_mount_early_boot_recovery.py`: solo estados
  interrumpidos verificables, ausencia de Kodi en /proc comprobada
  antes y después del bloqueo, y rollback con reconciliación OAuth.
- `lib/rclone_two_mount_legacy_cleanup.py` ya existente: elimina
  unit files legacy SOLO tras HEALTH v2 y `is-enabled` conocido,
  conservando respaldo privado.
- `lib/cloud_storage.py` ya existente: con estado active/unsafe
  no instala ni reintroduce unidades legacy.
- `lib/constants.py`: todos los flags de despliegue v2 aún False;
  esto es intencionado hasta ensayo físico para no migrar toda la flota
  por una actualización no verificada.

## Seguridad y límites pendientes

1. Regresión completa Ubuntu tras el último commit; objetivo *calculado*
   **837 tests** (811 anteriores + 26 nuevos). El recuento real es el de
   unittest, no asumir exactitud si la suite cambia.
2. Auditoría de `systemd-analyze verify` en sistema de archivos aislado,
   relación efectiva de `Wants/After` de CoreELEC, ruta Python y permisos.
   La instalación real de la unidad no se ha ejecutado en MASTER.
3. Ensayo de aborto SIGKILL y reinicio durante: prepared, cutover_started,
   install roots, install binds, mark active y partial cleanup.
   Verificar OAuth rotado y que no se habiliten ambas arquitecturas.
4. Verificar que los 6 servicios systemd generan exactamente el árbol
   previsto y que rclone reabre sus configs aisladas después del reboot.
5. Ejecutar piloto **solo en MASTER**, con operador, reproducción idle
   confirmada y backups OAuth protegidos. No usar CLIENTES como piloto.
6. Aprobar los flags del addon de release solo tras resultado real.
   El usuario distribuirá versión por su repositorio; Kodi actualizará
   automáticamente clientes y cada dispositivo migrará localmente.
7. No borrar carpeta /storage/.config/rclone/rclone.conf: sigue
   conteniendo remotos de otras funciones. Solo retirar los 4 archivos
   rclone legacy en system.d, no el conf canónico.

## Comando de regresión segura Ubuntu

```bash
cd ~/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m compileall -q service.cloud.masqelec/lib service.cloud.masqelec/tools service.cloud.masqelec/tests
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' > /tmp/masqelec-tests.log 2>&1
RESULT=$?
tail -n 20 /tmp/masqelec-tests.log
echo "FULL_REGRESSION_RESULT=$RESULT"
```

**No instalar el addon de develop en la flota como release.**
**No ejecutar chmod o systemctl de producción sin pruebas adicionales.**

```text
DEVELOP_CODE_INTEGRATED=YES
UBUNTU_811_TEST_BASELINE=PASS
NEW_REGRESSION=NOT_YET_EXECUTED
MASTER_READINESS=PASS_READ_ONLY
BOOT_RECOVERY_UNIT_ON_MASTER=NOT_INSTALLED
CUTOVER_EXECUTED=NO
RELEASE_FLAGS=ALL_FALSE
```
