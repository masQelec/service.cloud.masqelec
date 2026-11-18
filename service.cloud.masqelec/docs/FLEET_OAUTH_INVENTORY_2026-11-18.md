# Inventario OAuth de la flota — MASTER y CLIENTES
**18 de noviembre de 2026 · Fase de diagnóstico local, NO autorización de sondeo OAuth ni cutover.**

## Evidencia de partida

El MASTER KodiELEC ha confirmado **`CLEANUP=COMPLETE`** y **`LAB_RESULT=PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL`** en un laboratorio de 2 FUSE+4 bind con origen LOCAL ficticio. También ha confirmado el preflight legacy de solo lectura con las cuatro rutas correctas. Esto **no demuestra** que las dos conexiones crypt→OneDrive reales puedan convivir con otras instancias OAuth en MASTER y CLIENTES.

La función existente `tools/rclone_two_mount_real_probe_lab.py --real-probe` **bloquea** mientras haya montajes rclone y mientras no se haya demostrado la coordinación de tokens de otros dispositivos. Mantener esos bloqueos: incluso una operación `rclone lsf` puede renovar refresh tokens aunque solo lea datos remotos.

## Nuevo diagnóstico 100% local

`tools/rclone_two_mount_fleet_inventory.py` es autocontenido y solo admite `--inventory`. Lee los nombres de proceso en `/proc/<pid>/comm`, **inspecciona localmente** sus argumentos en `/proc/<pid>/cmdline` para clasificar `rclone mount` frente a otros subcomandos, y consulta `/proc/self/mountinfo` para contar montajes `fuse.rclone` en cuatro rutas legacy y dos raíces v2. **Nunca imprime argumentos, nombre de cuenta, PID o tokens.** No abre los ficheros de configuración, no ejecuta binarios rclone, no hace peticiones remotas y no modifica systemd ni montajes. **Exige root** para no declarar completo un `/proc` filtrado por permisos.

### Ejecutar en MASTER (solo lectura)

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/662bc955342fd9f4d1eaed3f3dab8eed753db5db/service.cloud.masqelec/tools/rclone_two_mount_fleet_inventory.py' -O /tmp/rclone_two_mount_fleet_inventory.py
python3 -m py_compile /tmp/rclone_two_mount_fleet_inventory.py
python3 /tmp/rclone_two_mount_fleet_inventory.py --inventory
```

Para cada CLIENTE se utiliza **el mismo script y comando**, exclusivamente si se tiene acceso administrativo a ese equipo. No reiniciar servicios, no parar rclone y no compartir archivos privados. Las salidas están diseñadas para copiarse sin secretos; aun así, revisar antes de publicarlas.

### Interpretación de salida

```text
LAB_MODE=FLEET_OAUTH_LOCAL_INVENTORY_READ_ONLY
REMOTE_REQUESTS=NO
CANONICAL_CONFIG_READ=NO
TOKEN_VALUES_PRINTED=NO
COMMAND_LINE_INSPECTED=YES_LOCAL_ONLY
PROCESS_ARGUMENTS_PRINTED=NO
MOUNT_OR_SYSTEMD_MUTATIONS=NO
DEVICE_ROLE=NOT_ATTESTED
ROOT=YES
PROC_INSPECTION=COMPLETE
MOUNTINFO_INSPECTION=COMPLETE
RCLONE_PROCESSES=<número>
RCLONE_MOUNT_PROCESSES=<número>
RCLONE_OTHER_PROCESSES=<número>
RCLONE_UNCLASSIFIED=<número>
RCLONE_FUSE_MOUNTS=<número>
LEGACY_MOUNT_TARGETS=<número>/4
V2_FUSE_ROOTS=<número>/2
STACKED_KODI_OR_V2_TARGETS=<número>
OTHER_RCLONE_FUSE_MOUNTS=<número>
SINGLE_SNAPSHOT_STABILITY=NOT_VERIFIED
OTHER_DEVICES_INSPECTED=NO
FLEET_OAUTH_COORDINATION=NOT_VERIFIED
REAL_OAUTH_PROBE_ALLOWED=NO
CUTOVER_AUTHORIZED=NO
INVENTORY_RESULT=PASS_READ_ONLY
```

`PASS_READ_ONLY` significa únicamente **inventario local legible**. No exige cero procesos rclone ni autoriza parar nada. En un MASTER legacy sano esperamos habitualmente cuatro montajes en sus rutas, pero **no presuponer** cuatro procesos por el tipo de unidades u otros usos de rclone. `RCLONE_OTHER_PROCESSES` no se debe confundir con un error: puede contener otros procesos activos, por ejemplo Google Drive. Cualquier `INCOMPLETE` exige investigar permisos y topología sin datos secretos.

**Limitaciones materiales:** una captura de `/proc` es instantánea, no bloquea nuevos escritores, no ve otros dispositivos, puede omitir ejecutables renombrados o tareas programadas que aún no hayan arrancado y no acredita la frescura ni la validez de ningún refresh token. Un cero absoluto en los recuentos **NO** equivale a una flota coordinada. La salida tampoco acredita por sí misma el rol MASTER/CLIENTE.

## Gates siguientes, sin saltos

1. Obtener inventario de MASTER y del conjunto **completo y conocido** de CLIENTES que comparten las mismas cuentas OAuth. Registrar qué dispositivo cumple cada rol sin añadir identificadores personales al repositorio.
2. Identificar **todas** las rutas de escritura de tokens (montajes, servicio cloud, importaciones, tareas programadas, scripts de mantenimiento, otros dispositivos). Establecer cómo se detienen y reanudan en una ventana aprobada, incluidas tareas Google Drive que escriben `rclone.conf`.
3. Definir un cierre de escritores verificable y la fuente exacta de los dos refresh tokens por cuenta **sin copiarlos al chat**. Conservar copia privada durable y rollback probado. Una segunda conexión sin estas garantías está prohibida.
4. Únicamente tras estos gates, preparar ensayo de 2 FUSE crypt→OneDrive con lectura exacta de un fichero conocido por cuenta, playback Kodi inactivo, sin escaneo general y rollback de las cuatro rutas originales.

**Estado:** `REAL_OAUTH_PROBE_ALLOWED=NO`, `CUTOVER_AUTHORIZED=NO`, flags `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`, `RCLONE_TWO_MOUNT_STAGING_ENABLED=False`, `RCLONE_TOKEN_SYNC_ENABLED=False`.

## Pruebas

Código `662bc955342fd9f4d1eaed3f3dab8eed753db5db`, CI: 647 pruebas previstas (624 previas + 23 pruebas de inventario y root). Verificar resultado en Actions antes de usar. Los tests usan `/proc` y mountinfo ficticios en directorios temporales, **no** leen las cuentas del MASTER ni CLIENTES.

**Handoff:** paso práctico siguiente: recibir el resumen de inventario LOCAL del MASTER, analizar recuentos y discrepancias, y continuar con CLIENTES sin arrancar OAuth v2. No repetir el laboratorio systemd local, que ya pasó físicamente.

## Resultado físico MASTER — 2026-11-18: PASS_READ_ONLY

Inventario REAL devuelto por el operador desde KodiELEC MASTER (sin credenciales ni argumentos expuestos):

```text
LAB_MODE=FLEET_OAUTH_LOCAL_INVENTORY_READ_ONLY
REMOTE_REQUESTS=NO
CANONICAL_CONFIG_READ=NO
TOKEN_VALUES_PRINTED=NO
COMMAND_LINE_INSPECTED=YES_LOCAL_ONLY
PROCESS_ARGUMENTS_PRINTED=NO
MOUNT_OR_SYSTEMD_MUTATIONS=NO
DEVICE_ROLE=NOT_ATTESTED
ROOT=YES
PROC_INSPECTION=COMPLETE
MOUNTINFO_INSPECTION=COMPLETE
RCLONE_PROCESSES=4
RCLONE_MOUNT_PROCESSES=4
RCLONE_OTHER_PROCESSES=0
RCLONE_UNCLASSIFIED=0
RCLONE_FUSE_MOUNTS=4
LEGACY_MOUNT_TARGETS=4/4
V2_FUSE_ROOTS=0/2
STACKED_KODI_OR_V2_TARGETS=0
OTHER_RCLONE_FUSE_MOUNTS=0
SINGLE_SNAPSHOT_STABILITY=NOT_VERIFIED
OTHER_DEVICES_INSPECTED=NO
FLEET_OAUTH_COORDINATION=NOT_VERIFIED
REAL_OAUTH_PROBE_ALLOWED=NO
CUTOVER_AUTHORIZED=NO
INVENTORY_RESULT=PASS_READ_ONLY
```

**Interpretación exacta:** el MASTER, durante esa lectura, tenía 4 procesos rclone de montaje y 4 entradas FUSE en las rutas legacy; ninguna raíz nueva activa, ningún FUSE extra ni apilamiento detectado. La inspección de /proc y mountinfo fue completa con privilegios root. **No acredita** validación de OAuth, asignación individual de procesos a cuentas, estabilidad temporal, inactividad futura de timers, ausencia de programas rclone renombrados, ni situación en CLIENTES. **No probar OAuth aún**: los escritores de montaje siguen activos.

**Gates:**
```text
MASTER_LOCAL_RCLONE_INVENTORY=PASS_READ_ONLY
MASTER_LEGACY_PATHS=4_OF_4
LOCAL_EXTRA_RCLONE_PROCESS=NOT_OBSERVED_IN_SNAPSHOT
CLIENT_FLEET_INVENTORY=NOT_RUN
FLEET_OAUTH_COORDINATION=NOT_VERIFIED
REAL_OAUTH_PROBE_ALLOWED=NO
CUTOVER_AUTHORIZED=NO
SYSTEMD_LOCAL_LAB=PASS_REAL
```

### Siguiente obtención de evidencia — clientes reales

Ejecutar el **mismo** `rclone_two_mount_fleet_inventory.py --inventory` (referencia fija de la sección anterior) en cada CLIENTE **que utilice las mismas cuentas**, con root y sin cambios systemd. Rotular la salida manualmente como `CLIENTE 1`, `CLIENTE 2`, etc.; no introducir hostname, IP, remotos, configuraciones o tokens en los informes públicos. No exigir `4/4` en CLIENTES: ese patrón se ha comprobado en MASTER y el cliente puede tener una distribución distinta. Guardar la cantidad real de clientes inventariados y contrastarla con el inventario de equipos conocidos antes de declarar cobertura.

Hasta que se identifiquen y coordinen **todos** los escritores potenciales entre dispositivos y ventanas programadas, no iniciar `lsf`, `rclone mount` extra, sondas OAuth ni transición. La existencia de cuatro rclone activos en MASTER impide interpretar un sondeo adicional como aislado.

## Resultado físico CLIENTE 1 — 2026-11-18: PASS_READ_ONLY

El operador identifica como **CLIENTE 1** el segundo dispositivo verificado (el script devuelve `DEVICE_ROLE=NOT_ATTESTED` porque no certifica el rol por sí solo). Salida recibida:

```text
LAB_MODE=FLEET_OAUTH_LOCAL_INVENTORY_READ_ONLY
REMOTE_REQUESTS=NO
CANONICAL_CONFIG_READ=NO
TOKEN_VALUES_PRINTED=NO
COMMAND_LINE_INSPECTED=YES_LOCAL_ONLY
PROCESS_ARGUMENTS_PRINTED=NO
MOUNT_OR_SYSTEMD_MUTATIONS=NO
DEVICE_ROLE=NOT_ATTESTED
ROOT=YES
PROC_INSPECTION=COMPLETE
MOUNTINFO_INSPECTION=COMPLETE
RCLONE_PROCESSES=4
RCLONE_MOUNT_PROCESSES=4
RCLONE_OTHER_PROCESSES=0
RCLONE_UNCLASSIFIED=0
RCLONE_FUSE_MOUNTS=4
LEGACY_MOUNT_TARGETS=4/4
V2_FUSE_ROOTS=0/2
STACKED_KODI_OR_V2_TARGETS=0
OTHER_RCLONE_FUSE_MOUNTS=0
SINGLE_SNAPSHOT_STABILITY=NOT_VERIFIED
OTHER_DEVICES_INSPECTED=NO
FLEET_OAUTH_COORDINATION=NOT_VERIFIED
REAL_OAUTH_PROBE_ALLOWED=NO
CUTOVER_AUTHORIZED=NO
INVENTORY_RESULT=PASS_READ_ONLY
```

**Resumen conjunto MASTER + CLIENTE 1:** cada equipo presenta cuatro procesos rclone clasificados como mount y cuatro montajes FUSE legacy, sin roots v2 ni apilamiento observado. Suman **8 procesos rclone mount y 8 montajes FUSE** en estos dos equipos, en dos snapshots tomados en momentos distintos; no se ha medido simultaneidad ni estabilidad temporal. Sin datos sobre otros clientes. Estos resultados NO verifican si los equipos comparten idénticos refresh tokens: el inventario no lee ni calcula huellas de credenciales. No permiten deducir ni autorizar una ventana de exclusión OAuth.

```text
MASTER_LOCAL_RCLONE_INVENTORY=PASS_READ_ONLY
CLIENT_1_LOCAL_RCLONE_INVENTORY=PASS_READ_ONLY
DEVICES_INVENTORIED=2
TOTAL_CLIENTS=NOT_CONFIRMED
FLEET_COVERAGE=NOT_VERIFIED
FLEET_OAUTH_COORDINATION=NOT_VERIFIED
REAL_OAUTH_PROBE_ALLOWED=NO
CUTOVER_AUTHORIZED=NO
```

**Siguiente paso:** confirmar el **número total de CLIENTES** que usan estas cuentas y continuar el inventario exclusivamente de lectura en los restantes. Si CLIENTE 1 es el único, aclarar que aun con cobertura local de ambos dispositivos hacen falta identificación y exclusión de otros escritores OAuth (servicios, timers, scripts, equipos externos) y un protocolo probado de pausa/reinicio antes de autorizar OneDrive real.

### 18/11/2026 — decisión de producto: actualización automática global vía addon, NO corte gradual por operador

El usuario aclara que **hay más CLIENTES que los dos equipos inventariados y todos comparten arquitectura**: NO desea parada ni migración manual uno por uno. El repositorio de addons de Kodi distribuirá una versión futura de `service.cloud.masqelec`; cada nodo adoptará localmente 2 FUSE + 4 bind cuando reciba la actualización, preservando los cuatro destinos de STRM. Kodi no actualiza todos simultáneamente (equipos apagados/con distintas configuraciones). MASTER publicará MQC2 desde `cloud.masqelec`; cada CLIENTE conservará sus tokens locales y recuperará **solo en error OAuth confirmado** la credencial del MASTER correspondiente, con validación/rollback. **No forzar inventario exhaustivo o parada de toda la flota como requisito del despliegue de addon.**

GAPS confirmados por lectura de código: `rclone_two_mount_live_adapter.py` no está conectado a `service.py`; flags de release False; `rclone_token_sync.tick` se corta en v2 activo, así que publicación MASTER v2 y recuperación CLIENT v2 **no están implementadas**; el addon aún tiene `version=2.3.1` en `develop/main`, y es necesario empaquetado/metadatos del repo para actualizar; `cloud_storage` descarga MQC2 al arrancar y actualmente conserva tokens locales, pero la recuperación v2 por cuenta aislada no está conectada. **No autorizar release todavía**. [Decisión y gates](AUTO_UPDATE_TWO_MOUNT_ARCHITECTURE_2026-11-18.md).
