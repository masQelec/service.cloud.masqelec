# Recuperación temprana de montajes en KodiELEC — 19/11/2026

**Estado:** candidato de código y pruebas sintéticas, sin habilitar systemd ni ejecutar operaciones en MASTER.
La flota usa TX3 / X96 X4; el sistema es un fork CoreELEC, `/storage` ext4
persistente y la arquitectura nueva es 2 FUSE + 4 bind.

## Decisión de disponibilidad: recuperación NO crítica (operador, 19/11/2026)

**La disponibilidad de KodiELEC y de los demás servicios tiene prioridad
sobre los montajes OneDrive.** El operador confirma que si el journal
está corrupto, la autenticación no permite recuperar o los montajes quedan
ausentes, el sistema debe continuar arrancando; únicamente habrá
indisponibilidad temporal de los archivos multimedia remotos.

Requisitos:
- Fallo de recuperación = **media no disponible**, NO fallo de arranque
  del sistema, Kodi, Tvheadend, Docker, red o servicios independientes.
- Nunca utilizar `Requires=masqelec-v2-recovery.service` en `kodi.service`.
  Preferir `Wants=` y `After=` cuando el servicio se integre, validando
  con `systemd-analyze verify` y `systemctl show` en laboratorio.
- La espera de una recuperación debe tener límite acotado y cancelación
  compatible con systemd. Los estados ilegibles deben abortar rápidamente,
  sin intentar montar por adivinación.
- No reactivar automáticamente legacy cuando v2 tenga montajes activos
  o el estado sea desconocido: evitar rutas montadas simultáneamente.
- La aplicación y otros servicios siguen disponibles aunque las rutas
  de OneDrive carezcan de contenido. Informar de la incidencia en el
  log y permitir un reintento posterior bajo condiciones verificadas.
- Si se diseñan dependencias para esperar el intento de recuperación,
  un fallo del recuperador NO se propagará como dependencia obligatoria.
- Pre-Kodi no significa secuestrar el arranque completo: acotar tanto
  `TimeoutStartSec=` como los timeouts de las operaciones de systemctl
  y desmontajes que se invoquen. Una dependencia `After=` **espera**;
  incluso con `Wants=` puede demorar Kodi hasta terminar/expirar.
- El coordinador de recuperación existente es candidato; ninguna unidad
  temprana está instalada, y no hay evidencia de pruebas de apagado real.

**Esta decisión sustituye** cualquier recomendación anterior de bloquear
el arranque de Kodi ante un journal corrupto o recuperación imposible.

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

## Evidencia de kodi.target (operador, 19/11/2026)

La salida íntegra recibida para `systemctl show kodi.target`:

```text
Requires=multi-user.target network-online.target graphical.target
Wants=kodi.service service.tvheadend43.service ledfix.service service.aml-vnc.service vfd-clock.service service.system.docker.service kodi-aml-hdmimonitor.service network-online.target
After=graphical.target kodi.service multi-user.target service.tvheadend43.service ledfix.service service.aml-vnc.service vfd-clock.service service.system.docker.service kodi-aml-hdmimonitor.service network-online.target
```

Estas propiedades corresponden a **kodi.target**, no prueban por sí mismas
las relaciones internas del propio **kodi.service**. No confundir la relación
`Wants` (débil) con `Requires` (fallo de unidad requerido puede afectar
al arranque de la solicitante), ni `Before/After` (solo orden) con inclusión
en la transacción de arranque.

Candidato de dependencia de recuperación, **no instalar** hasta integrar
ejecutor temprano y validar su entorno:
- `masqelec-v2-recovery.service`, `Type=oneshot`, `Before=kodi.service`,
  ordenado después de la inicialización del almacenamiento persistente.
- Drop-in persistente para `kodi.service` que solicite sin imponer fallo y ordene
  `masqelec-v2-recovery.service` (`Wants=` + `After=`; verificar
  condiciones de reinicio y tiempos máximos, NO usar `Requires=`).
- El ejecutor requiere ruta estable accesible pre-Kodi, código de salida
  que marque fallo cuando la recuperación sea insegura, y **no depender
  de un addon que únicamente se importe después de Kodi**.
- `kodi.target` incluye Tvheadend, Docker y VNC: no modificar estas
  dependencias durante la intervención de recuperación.
- Ensayar fallos y recuperación en entorno aislado; no habilitar en MASTER
  con pruebas únicamente de mocks.

Comprobación pendiente, sin paginador y solo lectura:

```sh
SYSTEMD_PAGER=cat systemctl cat kodi.service --no-pager
SYSTEMD_PAGER=cat systemctl show kodi.service -p Wants -p Requires -p After -p Before -p DropInPaths -p UnitFileState --no-pager
```

## Integración de la versión automática (candidato develop, pendiente de prueba física)

Componentes nuevos:

- `lib/rclone_two_mount_boot_install.py`: antes del primer cutover,
  instala exclusivamente `masqelec-v2-recovery.service` y el drop-in
  `kodi.service.d/50-masqelec-v2-recovery.conf` bajo
  `/storage/.config/system.d`, con comprobación de symlinks, propietario,
  integridad de archivos preexistentes y verificación de las relaciones
  `Wants` y `After` en el `systemctl show` fusionado tras daemon-reload.
  No escribe sobre archivos de terceros. Si la integración de arranque
  falla, se bloquea **el corte de montajes**, NO Kodi.
- `tools/rclone_two_mount_early_boot_run.py`: devuelve 0 tanto si
  logra recuperar como si el contenido remoto queda inaccesible. Emite
  solo estados conocidos; no imprime rutas, tokens ni secretos.
- `lib/rclone_two_mount_active_maintenance.py`: en cada ciclo habilitado,
  distingue 2 FUSE + 4 bind sanos (no tocar) de unidades nuevas realmente
  ausentes (arrancar solo las ausentes). Rechaza ruta ocupada, legacy
  concurrente, journal inconsistente y configuraciones aisladas inseguras.
  La verificación del layout continúa basada en mountinfo.
- `lib/rclone_two_mount_autostart.py`: en estado legacy exige boot
  installer `READY` antes de entrar al motor de cutover; en estado
  activo ejecuta mantenimiento antes de retirar definitivamente los
  cuatro unit files antiguos. El mantenimiento activo **no depende**
  de encontrar dos muestras multimedia; el primer corte y la retirada
  irreversible sí requieren las muestras de salud.
- `lib/cloud_storage.py`: mantiene su guardia anterior: no descarga,
  reinicia ni recrea legacy cuando el estado es `active` o `unsafe`.
  Es indispensable mantenerla durante futuras versiones del addon.
- `lib/rclone_two_mount_legacy_cleanup.py`: solo retira las cuatro
  unidades antiguas cuando v2 está activo y sano, y legacy no está activo
  ni habilitado; conserva respaldo privado para recuperación manual.
  El corte original deshabilita legacy antes de detenerlo.

**Política de disponibilidad:** el servicio usa `Before=kodi.service` y
drop-in `Wants=masqelec-v2-recovery.service` +
`After=masqelec-v2-recovery.service`, **nunca Requires**.
`TimeoutStartSec=45`: el arranque puede esperar hasta ese límite,
pero si se agota, Kodi seguirá arrancando y el multimedia puede faltar.
El proceso de recuperación debe seguir siendo reiniciable y seguro
tras corte del propio servicio.

**Nota:** `Wants + After` solo funcionará si KodiELEC efectivamente
importa el drop-in del directorio persistente. Lo verifica el instalador,
pero falta prueba real en MASTER, prueba de reinicio y revisión de
`systemd-analyze verify`. **No se han activado los flags de release.**

### Gates que siguen en NO

```text
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED=False
RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED=False
RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED=False
RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED=False
PRODUCTION_CUTOVER_EXECUTED=NO
SYSTEMD_UNIT_INSTALLED_ON_MASTER=NO
```

Activar todos a la vez antes de completar el ensayo con cortes
simulados/rollback/OAuth real expondría a toda la flota cuando el usuario
publique la actualización. El addon será automático **en la versión de
release validada**, no en este candidato de `develop`.
