# Recuperación temprana de montajes en KodiELEC — 19/11/2026

**Estado:** candidato de código y pruebas sintéticas, sin habilitar systemd ni ejecutar operaciones en MASTER.
La flota usa TX3 / X96 X4; el sistema es un fork CoreELEC, `/storage` ext4
persistente y la arquitectura nueva es 2 FUSE + 4 bind.

## Problema

En una interrupción después de `mark_cutover_started`, el addon habrá
deshabilitado los cuatro servicios legacy para evitar conflicto. El boot
puede continuar sin montajes. `service.py` puede detectar el journal
por `boot_guard`, pero la restitución del adaptador existente dependía de
`Player.GetActivePlayers` de Kodi, que no está disponible antes de iniciar
Kodi. Debe evitarse presentar bloqueo de arranque como recuperación.

## Implementación actual

`lib/rclone_two_mount_early_boot_recovery.py`:
- `interrupted_state(parent, state_path)` valida **journal y marcador**.
  Solo estados `cutover_started` o `rollback_required` con marcador
  `unsafe` admiten preparación del rollback. `active` no se revierte.
  Estados parcialmente escritos o ilegibles exigen intervención humana.
- `kodi_process_absent()` inspecciona `/proc` y **falla cerrado** si hay
  proceso de Kodi o lectura incierta. No interpreta ausencia de RPC como
  reproducción inactiva.
- `execute(... authorized=False, rollback_verified=False)` no opera
  por defecto. Con autorización, banderas de feature, root, journal
  interrumpido y ausencia de Kodi **verificada dos veces**, bloquea el
  journal y llama `LocalAdapter.recover_pending_from_disk()`.
  El mecanismo existente reconcilia los snapshots OAuth al detener los
  escritores y restaura legacy solo cuando cumple los gates.
- Un callback RPC vacío **sintético** solo se usa en ese escenario
  *pre-Kodi*, nunca dentro de un Kodi vivo. La validación por procesos
  NO sustituye la garantía de orden systemd y no elimina por sí sola
  una carrera contra el inicio de Kodi.

`tools/rclone_two_mount_early_boot_probe.py --read-only`:
inspecciona journal y proceso Kodi sin credenciales, systemctl ni montajes;
es seguro ejecutarlo desde SSH con Kodi iniciado. `NO_PENDING` es esperado
antes del primer cutover.

## Antes de instalar un servicio de recuperación

1. Identificar nombre de unidad Kodi y su `systemctl show` en MASTER:
   `systemctl status kodi.service` / `systemctl list-unit-files | grep -i kodi`.
2. Diseñar dependencia **obligatoria** con orden `Before` para impedir
   que Kodi arranque durante la recuperación. Solo `Before=` NO aporta
   dependencia de ejecución; hay que validar Requires/Wants concretos
   en el sistema real. No modificar unidades de Kodi antes de verificar.
3. Garantizar que el script vive en ruta persistente accesible antes de Kodi
   y que el entorno de Python/CoreELEC permite cargar bibliotecas del addon.
4. Validar en laboratorio con `systemctl`/FUSE simulados los estados tras
   SIGKILL, fase activa parcial, token rotado, falta de `account*.conf`,
   journal corrupto, proceso Kodi concurrente y reinicio real.
5. Realizar ensayo con MASTER y operador presente, con rollback manual
   documentado antes de habilitar autorrecuperación.
6. No activar `RCLONE_TWO_MOUNT_FEATURE_ALLOWED` ni
   `RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED` por las pruebas sintéticas.

## Próximas comprobaciones seguras MASTER

```sh
systemctl list-unit-files | grep -i kodi
systemctl show kodi.service -p Id -p FragmentPath -p Wants -p Requires -p Before -p After
```

No ejecutar `systemctl stop`, `disable`, montaje real ni recuperación
a través de este documento.

```text
UBUNTU_798_REGRESSION=PASS_CONFIRMED_BEFORE_THIS_COMMIT
EARLY_BOOT_CODE=STAGED_DEVELOP
EARLY_BOOT_SYSTEMD_UNIT=NOT_INSTALLED
EARLY_BOOT_REAL_REBOOT=NOT_VERIFIED
CUTOVER_AUTHORIZED=NO
```

## Evidencia MASTER recibida (19/11/2026)

El operador confirma `Ran 811 tests ... OK` y `FULL_REGRESSION_RESULT=0` en Ubuntu.
El equipo MASTER devuelve:

```text
Id=kodi.service
FragmentPath=/usr/lib/systemd/system/kodi.service
Requires=sysinit.target system.slice graphical.target
Wants=kodi-cleanlogs.service network-online.target kodi-autostart.service ...
Before=kodi-aml-hdmimonitor.service shutdown.target kodi.target
After=locale.service basic.target opentee_linuxdriver.service graphical.target ...
```

**La salida de Wants/After estaba truncada por el terminal/paginador.** No inferir
la totalidad de relaciones de systemd a partir del fragmento.

La ubicación `/usr/lib/systemd/system/kodi.service` es del sistema de imagen
(solo lectura); **nunca editarla**. Un servicio de recuperación futuro se
instalará en `/storage/.config/system.d` y deberá añadirse expresamente
a la transacción de arranque de `kodi.service`; `Before=kodi.service`
por sí solo solo ordena unidades que ya estén en la misma transacción.
Poner `WantedBy=multi-user.target` no garantiza por sí solo
ninguna activación obligatoria si se reinicia Kodi manualmente.

### Preflight de dependencias: exclusivamente lectura y sin paginador

```sh
export SYSTEMD_PAGER=cat
systemctl show kodi.service -p Id -p FragmentPath -p DropInPaths -p UnitFileState -p Wants -p Requires -p Before -p After --no-pager
systemctl cat kodi.service --no-pager
systemctl show kodi.target -p Wants -p Requires -p After --no-pager
```

Los comandos no modifican el sistema y deben ejecutarse antes de diseñar y
ensayar una dependencia persistente. **No instalar drop-in, no habilitar
servicio, no reiniciar Kodi** sin un laboratorio controlado.

Notas upstream: CoreELEC incluye ejemplos de servicios que usan
`Before=kodi.service` y unidades en `/storage/.config/system.d`.
- https://github.com/CoreELEC/CoreELEC/blob/coreelec-22/packages/sysutils/systemd/config/system.d/cifs.mount.sample
- https://discourse.coreelec.org/t/stuck-on-startup-logo/13816
- https://www.freedesktop.org/software/systemd/man/latest/systemd.unit
