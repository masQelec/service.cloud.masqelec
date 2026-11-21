# G3-AM — Preflight de binario Ubuntu y laboratorio paralelo (21/11/2026)

## Alcance
Continuación de G3-AL. Evidencia aportada por el operador desde Ubuntu, comandos de solo lectura. No se ha lanzado el binario parcheado, ni creado una segunda instancia, ni modificado Tvheadend/Kodi/playlist originales.

## Evidencia observada
- Laboratorio: `/home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab`.
- `docker compose ps`: `masqelec-pvr-g3ab-tvh-1` y `masqelec-pvr-g3ab-streams-1` activos (Up 10 hours), ambos con cero acciones de reinicio reportadas en este gate.
- TVH original: `lscr.io/linuxserver/tvheadend:latest`, `linux/amd64`, ID visible `7f5d04ed7ea7`, puertos loopback `19991:9981`, `19992:9982`.
- Streams: `nginx:alpine`, `linux/amd64` sin puerto publicado.
- Existen marcador sintético, playlist, configuración TVH, perfil Kodi y las dos capturas HTSP previas. Existencia no equivale a validar contenidos.
- Checkout: `/home/ubuntu/tvheadend-g3al-upstream`, HEAD `8837853a6`; git status ` M src/input/mpegts/iptv/iptv_auto.c` (parche aplicado).
- Ejecutable: `build.linux/tvheadend`; `file` ELF 64-bit PIE x86-64, GNU/Linux glibc dinámico (`/lib64/ld-linux-x86-64.so.2`), no stripped.
- `ldd` resuelve `libssl.so.3`, `libcrypto.so.3`, `libz.so.1`, `libm.so.6`, `libc.so.6`, `libzstd.so.1`. No reportó ninguna biblioteca `not found` **en el host**.
- `--version`: `4.3-2897~g8837853a-dirty`; sufijo dirty compatible con el parche local.
- SHA-256 del binario: `b94c205632ab1dc8ad8e4d71d9c127ddae518fd28c3381919b5974de65aa753a`.
- El comando de preflight terminó con `G3AM_READ_ONLY_PREFLIGHT=COMPLETED`, que es marcador de recorrido, **no** acreditación automática de todos los invariantes.

## Conclusión limitada
`G3AM_HOST_BINARY_ARCH=PASS_X86_64`; `G3AM_HOST_LDD_RESOLUTION=PASS`; `G3AM_VERSION=PASS_VERIFIED`.
**No** está demostrada compatibilidad de ABI/runtime con contenedor LinuxServer, capacidad de aceptar HTSP, envío de `channelUpdate`, actualización de Kodi o preservación de IDs. Configuración host compilada con funciones reducidas respecto a distribución final.

## Siguiente gate: aislamiento — primero inventario read-only
1. Confirmar puertos candidatos `127.0.0.1:29991/29992` libres y la topología de red y modo de acceso a `http://streams/ch1.ts` sin publicar credenciales.
2. Evaluar host glibc + configuración aislada frente a nuevo contenedor builder/runtime compatible. No copiar binario Ubuntu directamente a LinuxServer.
3. Planificar snapshot/copia privada de configuración, referencias de playlist y cliente Kodi separado; mantener intactos `runtime/tvh_config`, `runtime/kodi_home/.kodi` y los puertos originales.
4. No ejecutar `prepare.py` en el laboratorio original ni iniciar servidores paralelos hasta establecer aislamiento y rollback.
5. Posteriormente demostrar `channelUpdate` en **misma sesión HTSP** sin SYN/reconexión, respuesta Kodi sin playback, y preservación de UUID, servicios, identificadores Kodi, autoname, grupos/favoritos. Comparar antes/después en instancia aislada; no tratar UUID anteriores como obligatorios si la instancia se ha inicializado con otros.
6. Sin modificar production/CoreELEC. EPG-01 queda para fase posterior.

## Estados
```
G3AM_LAB_COMPOSE_RUNNING=PASS_OBSERVED
G3AM_LAB_STATE_FILES=PRESENT
G3AM_HOST_BINARY_ARCH=PASS_X86_64
G3AM_HOST_DEPENDENCIES=PASS_LDD_NO_MISSING
G3AM_BINARY_VERSION=4.3-2897~g8837853a-dirty
G3AM_BINARY_SHA256=b94c205632ab1dc8ad8e4d71d9c127ddae518fd28c3381919b5974de65aa753a
G3AM_BINARY_RUNTIME=NOT_TESTED
G3AM_PARALLEL_TVH=NOT_STARTED
G3AM_HTSP_HOT_RENAME=NOT_TESTED
G3AM_KODI_UPDATE=NOT_TESTED
G3AM_CORELEC_BUILD=NOT_STARTED
G3AM_PRODUCTION_DEPLOY=NO
```

Documentos: `HANDOFF_TVH_CUSTOM_CORELEC_EPG_2026-11-21.md`, `RUNBOOK_G3AB_UBUNTU_LAB_2026-11-21.md`, `PVR_G3AL_TVH_PATCH_CANDIDATE_2026-11-21.md`.

## G3-AM continuación — comprobación de puertos y red (operador, 21/11/2026)

Salida read-only:
```text
PORT_29991=BIND_AVAILABLE
PORT_29992=BIND_AVAILABLE
NETWORK=masqelec-pvr-g3ab_pvr_g3ab
NETWORK_DRIVER=bridge
TVH_IMAGE=sha256:7f5d04ed7ea7f58cd50c2cf11a79d0823fa0a4aa4f6c64478360b9e3a8027c28
STREAMS_IMAGE=sha256:62d1c420c34ae91f7bffd349903cd6846806b835129c8b7ba2da28b3be323cd1
DOCKER=29.1.3 (29.1.3-0ubuntu4.1)
COMPOSE=2.40.3+ds1-0ubuntu1
G3AM_NETWORK_PREFLIGHT=COMPLETED
```

Los puertos estaban libres para `bind(127.0.0.1)` durante la medición, pero eso **no los reserva**. Los contenedores TVH/streams están conectados a la misma red bridge. No se ha demostrado todavía DNS interno para un futuro contenedor nuevo, ni un mecanismo válido de importar playlist sin tocar la original.

**Decisión de diseño:** segunda instancia aislada con config y playlist privadas, sin publicar más de 29991/29992 en loopback, preferentemente sobre runtime glibc compatible con el ELF Ubuntu, no reemplazar LinuxServer ni montar config original como RW. Si se utiliza el servidor web `streams` compartido, conectarlo a la red `masqelec-pvr-g3ab_pvr_g3ab` y validar alcance después. Para la actualización de playlist, confirmar que el origen será HTTP(S): el parche G3-AL deliberadamente no notifica rutas file/pipe, por falta de auditoría de locks. No iniciar ensayo rename desde una URL file:// y declarar fallo del parche. Antes de crear nada, identificar fuente/argumentos de inicio y rutas HTTP de playlist sin revelar credenciales.

```text
G3AM_PORTS_29991_29992=AVAILABLE_AT_SAMPLE
G3AM_SHARED_NETWORK=VERIFIED_BRIDGE
G3AM_STREAMS_ACCESS_FROM_NEW_TVH=NOT_TESTED
G3AM_HTTP_PLAYLIST_SOURCE=NOT_VERIFIED
G3AM_PARALLEL_TVH=NOT_STARTED
G3AM_HOT_RENAME=NOT_TESTED
```

## G3-AM — parámetros CLI y disponibilidad de imagen (operador, 21/11/2026)

La consulta read-only `docker image ls --filter reference='ubuntu:*'` no imprimió imágenes (no se constató ninguna imagen `ubuntu:*` local). `./build.linux/tvheadend --help` confirmó `--config`, `--user`, `--group`, `--bindaddr`, `--http_port`, `--htsp_port`, `--htsp_port2`, `--fork`, `--nobackup` y otros parámetros. El marcador de comando fue `G3AM_RUNTIME_SELECTION_PREFLIGHT=COMPLETED`.

**No** se comprobó aún la imagen Ubuntu concreta (versión de glibc), ni existe contenedor paralelo. Opción preferida: imagen compatible glibc con bind-mount binario solo lectura, identidad de usuario restringida, config/playlist propia; red existente para streams, HTTP playlist propia; sin tocar LinuxServer original. Antes de crearla, verificar release host, bibliotecas mínimas (GLIBC symbol requirements), red y recursos disponibles; no realizar descargas o instalaciones automáticamente.

```text
G3AM_TVH_CLI_FLAGS=VERIFIED
G3AM_LOCAL_UBUNTU_IMAGE=NOT_LISTED
G3AM_COMPATIBLE_RUNTIME_IMAGE=NOT_SELECTED
G3AM_PARALLEL_RUNTIME=NOT_STARTED
```

## G3-AM — ABI host y propuesta runtime Noble (operador, 21/11/2026)

```text
HOST=Ubuntu 26.04 resolute
HOST_GLIBC=2.43
BIN_GLIBC_MAX_REQUIRED=2.38
DOCKER_HOST_ARCH=x86_64
DOCKER_HOST_OS=Ubuntu 26.04.1 LTS
FREE_SPACE=/dev/sda2 321G available (64% used)
G3AM_RUNTIME_ABI_PREFLIGHT=COMPLETED
```

La exigencia de símbolo GLIBC máximo observada (2.38) **es inferior a glibc 2.39 de Ubuntu 24.04 noble**. Es una precondición favorable, no prueba ejecutable. Ubuntu Noble distribuye `libssl3t64` (SONAME libssl.so.3), `libzstd1` y `zlib1g`. Referencias públicas: https://packages.ubuntu.com/libssl3t64 y https://packages.ubuntu.com/noble-updates/libs/.

Añadido archivo `lab/pvr_g3ab/g3am/Dockerfile.runtime` en develop: runtime Ubuntu 24.04 con bibliotecas, sin copiar binario a imagen, usuario 1000 y ENTRYPOINT del binario montado read-only. **No modifica el Compose original**. No contiene la fuente ni reconstruye TVH, no publica puertos y por sí mismo no ejecuta servicios.

### Siguiente gate operativo (G3-AM-RUNTIME-SMOKE)

Desde la carpeta del repositorio, construir imagen experimental dedicada y comprobar el binario con `--version` y red `none`. La imagen puede descargarse, consumir disco y requerir red; **no toca los contenedores originales**, pero no es read-only respecto al almacén Docker. Comprobar con `docker image inspect` la imagen generada después. El ensayo sigue sin crear configuración o servidor.

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec || exit 2
git pull --ff-only origin develop || exit 2
docker build --pull -f service.cloud.masqelec/lab/pvr_g3ab/g3am/Dockerfile.runtime \
  -t masqelec/tvh-g3am-runtime:noble \
  service.cloud.masqelec/lab/pvr_g3ab/g3am || exit 2
BIN=/home/ubuntu/tvheadend-g3al-upstream/build.linux/tvheadend
test -f "$BIN" && test -x "$BIN" || exit 2
test "$(sha256sum "$BIN" | awk '{print $1}')" = "b94c205632ab1dc8ad8e4d71d9c127ddae518fd28c3381919b5974de65aa753a" || exit 2
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$BIN,target=/opt/g3al/tvheadend,readonly" \
  masqelec/tvh-g3am-runtime:noble --version || exit 2
echo G3AM_RUNTIME_BINARY_SMOKE=PASS
```

El código anterior solo declara PASS si el proceso dentro de Docker termina con código cero. Si falla, no declarar compatibilidad del runtime. Antes de arrancar TVH habrá un gate separado de configuración privada, playlist HTTP, red y rollback. No usar este Dockerfile para CoreELEC.

```text
G3AM_NOBLE_ABI_STATIC_ASSESSMENT=COMPATIBLE_ON_GLIBC_VERSION
G3AM_RUNTIME_DOCKERFILE_COMMITTED=YES
G3AM_RUNTIME_IMAGE_BUILT=NO_OPERATOR_RESULT
G3AM_RUNTIME_BINARY_SMOKE=NOT_TESTED
G3AM_PARALLEL_TVH=NOT_STARTED
```

## G3-AM — runtime smoke Docker confirmado por operador (21/11/2026)

Tras construir la imagen de laboratorio definida en `lab/pvr_g3ab/g3am/Dockerfile.runtime`, el operador comunicó:

```text
G3AM_BINARY_HASH=PASS
/opt/g3al/tvheadend: version 4.3-2897~g8837853a-dirty
G3AM_RUNTIME_BINARY_SMOKE=PASS
```

El binario Ubuntu parcheado se ejecutó con `--version` dentro del contenedor Ubuntu 24.04, con `--network none`, rootfs `--read-only`, `--cap-drop ALL`, `no-new-privileges` y bind mount del ejecutable en lectura. Esto demuestra compatibilidad suficiente para **esa ejecución de versión**, no capacidad de inicializar la configuración ni comportamiento HTTP/HTSP real.

**Gate siguiente (aún read-only):** inspeccionar sin revelar secretos el tipo de origen de la M3U en configuración original de IPTV Auto, rutas y presencia de un servidor de playlist HTTP accesible desde red Docker, y el estado del perfil de Kodi independiente. Evitar copiar indiscriminadamente configuraciones con credenciales; planificar copia coherente y redacción de destinos. Si el origen actual es `file://`, preparar playlist HTTP propia en G3-AM; el parche restringe eventos a HTTP(S).

```text
G3AM_BINARY_IN_CONTAINER_VERSION=PASS
G3AM_PARALLEL_TVH_BOOT=NOT_TESTED
G3AM_HTSP_CHANNELUPDATE=NOT_TESTED
G3AM_KODI_HOT_UPDATE=NOT_TESTED
```

## G3-AM — Corrección de localización de configuración IPTV (21/11/2026)

El operador ejecutó un script diagnóstico anterior que asumía `runtime/tvh_config/iptv` como único directorio. Resultado: `G3AM_IPTV_CONFIG=NOT_FOUND`. **No inferir ausencia ni pérdida de configuración:** la ruta fue incorrectamente presupuesta por el diagnóstico. Tvheadend habitualmente organiza datos IPTV bajo subárboles `input/iptv/networks`, y LinuxServer puede ubicar config bajo niveles adicionales. Hay que inspeccionar la estructura realmente montada mediante una búsqueda limitada de directorios en lectura y, solo después, leer claves de archivos JSON de redes sin publicar URL completa, credenciales ni nombres de archivos que puedan contener secretos. Esta corrección reemplaza la inferencia del script anterior; no se ha modificado el estado del laboratorio.

```text
G3AM_IPTV_CONFIG_ORIGINAL=UNKNOWN
G3AM_PREVIOUS_PATH_ASSUMPTION=INVALID
G3AM_ORIGINAL_CONFIG_MISSING=NOT_PROVEN
G3AM_LAB_MODIFIED=NO
```

## G3-AM — estructura IPTV localizada (operador, 21/11/2026)

La comprobación de estructura, sin lecturas de secretos, devolvió:

```text
IPTV_DIRECTORIES=4
IPTV_DIR=input/iptv
IPTV_DIR=input/iptv/networks
IPTV_DIR=input/iptv/networks/4a86445d515cfeb6dda45f45e2ee561d
IPTV_DIR=input/iptv/networks/4a86445d515cfeb6dda45f45e2ee561d/muxes
G3AM_CONFIG_DISCOVERY=COMPLETED
```

**Corrección cerrada**: la raíz IPTV real es `runtime/tvh_config/input/iptv/networks`, no `runtime/tvh_config/iptv`. Hay una carpeta de red identificada; el contenido y validez de sus ficheros aún deben verificarse. Siguiente auditoría limitada: leer únicamente metadatos no sensibles del fichero de red (o del esquema de nivel superior que realmente exista); emitir nombres de claves permitidas y esquema de URL, nunca URL completa ni tokens. Contar muxes sin volcar su contenido. No modificar ni copiar el volumen original en escritura.

```text
G3AM_IPTV_DIRECTORY_DISCOVERY=PASS
G3AM_IPTV_NETWORK_CONFIG_VALUES=NOT_TESTED
G3AM_HTTP_PLAYLIST_SOURCE=NOT_VERIFIED
G3AM_PARALLEL_TVH=NOT_STARTED
```

## G3-AM — origen M3U original y preparación instancia aislada (operador, 21/11/2026)

Auditoría de red `runtime/tvh_config/input/iptv/networks/4a86445d515cfeb6dda45f45e2ee561d` devolvió:

```text
MUX_COUNT=2
bouquet=True
channel_number=0
enabled=True
max_streams=0
refetch_period=1
url_SCHEME=file
G3AM_NETWORK_METADATA=COMPLETED
```

**Hallazgo esencial**: la playlist original utiliza esquema `file`, mientras el parche G3-AL restringe la nueva notificación a `http`/`https`; no confundir fallo futuro de HTTP con el comportamiento de la red original, ni considerar válida una prueba de parche activada mediante file://. La red original y sus dos muxes **no** se modifican.

En `lab/pvr_g3ab/g3am/` se versionaron:
- `compose.yaml`: proyecto separado `masqelec-pvr-g3am`, contenedor TVH que monta el binario G3-AL read-only y su propia config `../runtime/g3am/tvh_config`, servicios en red externa `masqelec-pvr-g3ab_pvr_g3ab`, puertos HTTP/HTSP localhost `29991/29992`; contenedor nginx `playlist` que sirve exclusivamente `../runtime/g3am/playlist`, alias `g3am-playlist`. La imagen de TVH es la runtime Noble verificada en smoke. No monta la configuración ni playlist original.
- `prepare.py`: crea `runtime/g3am` tras comprobar marcador sintético; `init` falla si ya existe M3U para no pisarla; `baseline` y `rename` escriben únicamente la playlist privada con CUIDs `g3am-001/002`, URL de stream ya existente `http://streams/ch1.ts`/ch2.ts y nombre Alpha variable. No ejecutarlo hasta fijar baseline, y nunca usar `lab/pvr_g3ab/prepare.py` para ensayo G3-AM.

**Advertencia de método**: La red IPTV de la nueva instancia debe configurarse explícitamente como **IPTV Automatic Network** con URL `http://g3am-playlist/playlist.m3u` y refetch 1 min; levantar servicios no configura por sí solo IPTV. No copiar datos ni identidades antiguas: los IDs se baselinarán dentro de la nueva instancia. No generar un `channelUpdate` de rename si los canales no tienen autoname y mapeo verificados. La segunda Kodi debe tener perfil propio, no compartir `runtime/kodi_home/.kodi`.

### Gate de arranque controlado propuesto

Comandos en el Ubuntu operador, con efectos solo en `runtime/g3am` y nuevo proyecto Docker. El operador debe revisar config de Compose antes de iniciar:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec || exit 2
git pull --ff-only origin develop || exit 2
cd service.cloud.masqelec/lab/pvr_g3ab || exit 2
python3 g3am/prepare.py init || exit 2
docker compose -f g3am/compose.yaml config --quiet || exit 2
docker compose -f g3am/compose.yaml up -d playlist tvh || exit 2
docker compose -f g3am/compose.yaml ps
```

**Rollback exclusivo G3-AM:** `docker compose -f g3am/compose.yaml down` (sin `-v`, sin `--remove-orphans` contra el proyecto original), conservar `runtime/g3am` para diagnóstico. No ejecutar `docker compose down` sin `-f g3am/compose.yaml`.

Si el arranque falla, registrar un extracto sanitizado de logs de G3-AM (sin tokens, URLs ni credenciales), diagnosticar antes de cambiar permisos o ejecutar root. Guardas: ruta exacta de binario, digest esperado, puertos libres, red externa aún existente, directorio creado por usuario 1000. El init es un cambio de almacenamiento **limitado al runtime privado** y no equivale a prueba HTSP ni Kodi.

```text
G3AM_ORIGINAL_PLAYLIST_SCHEME=FILE_VERIFIED
G3AM_ORIGINAL_IPTV_MUX_COUNT=2
G3AM_ORIGINAL_REFETCH_PERIOD=1
G3AM_SEPARATE_COMPOSE=COMMITTED_NOT_OPERATOR_VALIDATED
G3AM_SEPARATE_PLAYLIST_GENERATOR=COMMITTED_NOT_OPERATOR_VALIDATED
G3AM_PARALLEL_TVH=NOT_STARTED
G3AM_HTTP_PLAYLIST=NOT_RUNNING
G3AM_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — primer arranque, HTTP sin respuesta (operador, 21/11/2026)

Tras ejecutar el bloque propuesto de preparación, arranque y curl:
```text
G3AM_HTTP_CODE=000
G3AM_BOOT_COMMANDS=COMPLETED
```

El operador **no proporcionó** salida de `docker compose ps`, exit codes ni logs. `curl 000` prueba ausencia de respuesta HTTP válida, no demuestra si falló el proceso TVH, el bind o el transporte. Marcador `COMPLETED` no es PASS. En este punto **no** reejecutar `up`, no regenerar playlist, no tocar G3-AB y no modificar config ni permisos a ciegas.

Siguiente paso exclusivamente read-only: `docker compose -f g3am/compose.yaml ps -a` con IDs, status, exit-code y Health (sin volcar env/volúmenes); `docker inspect` limitado a State.Status, State.ExitCode, State.Error (sanitizar si contiene rutas sensibles); estado de puertos con `ss -ltn`; búsqueda de firmas de error en logs solo de contenedores G3-AM con supresión de posibles secretos. No volcar logs completos ni URLs. A partir de evidencia real, elegir corrección mínima.

```text
G3AM_HTTP_FIRST_PROBE=FAIL_HTTP_000
G3AM_TVH_PROCESS_STATUS=UNKNOWN
G3AM_G3AB_ORIGINAL_MODIFIED=NOT_REPORTED
G3AM_HTSP_HOT_RENAME=NOT_TESTED
```

## G3-AM — clasificación de primer arranque TVH (operador, 21/11/2026)

Resultado de inspección de solo lectura, posterior a `HTTP_CODE=000`:

```text
G3AM_PLAYLIST_CONTAINER=running EXIT=0 RESTARTS=0
G3AM_TVH_CONTAINER=exited EXIT=134 OOM=false RESTARTS=0
PORT_29991=NOT_CONNECTABLE
PORT_29992=NOT_CONNECTABLE
G3AM_TVH_LOG_LINES=21 LOG_QUERY_RC=0
G3AM_PLAYLIST_LOG_LINES=26 LOG_QUERY_RC=0
PERMISSION_DENIED=0
CONFIG_ERROR=0
BIND_ERROR=0
MISSING_LIBRARY=0
SEGFAULT=0
FATAL_ERROR=0
PROCESS_EXIT=0
G3AM_DIAGNOSTIC=COMPLETED
```

**Diagnóstico:** Tvheadend no arranca como servidor; Docker exit 134 es **compatible** con SIGABRT, pero sin mensaje de abort/assert ni señal confirmada no atribuir a parche, permisos, memoria, configuración o dependencias. El clasificador anterior solo buscó patrones parciales y puede omitir assertion/abort/stack traces. Nginx sí continúa activo. No hacer `up/restart/down`, no borrar configuración ni cambiar permisos hasta recuperar evidencia concreta. Siguiente gate: capturar **solo** log TVH (21 líneas) con sanitización local de URLs, tokens y credenciales, extracto de mensajes assertion/abort y últimas líneas relevantes; verificar identidad UID/mode del directorio privado sin modificaciones. Compartir logs sanitizados, no completos en bruto.

```text
G3AM_TVH_BOOT=FAIL_EXIT_134
G3AM_PLAYLIST_SERVICE=RUNNING
G3AM_TVH_PORTS=NOT_CONNECTABLE
G3AM_ABORT_CAUSE=UNKNOWN
G3AM_HTTP_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — causa inmediata del aborto TVH acotada por log (operador, 21/11/2026)

El operador proporcionó log filtrado del único contenedor TVH G3-AM. Secuencia:
```text
INFO config: Using configuration from '/config'
INFO http: Starting HTTP server 0.0.0.0:9981
INFO htsp: Starting HTSP server 0.0.0.0:9982
INFO config: loaded
INFO config: scanfile (re)initialization with path <none>
ALERT profile: no default streaming profile! reinstall data files
ALERT CRASH: Signal: 6 in PRG: /opt/g3al/tvheadend
... pthread_kill, gsignal, abort ...
UID=1000 GID=1000 MODE=775 TYPE=directory
EXIT=134 OOM=false
```

Se confirma SIGABRT y ausencia de perfil streaming predeterminado **durante la inicialización**; no se demuestra todavía si es ausencia de data files, configuración interna vacía o parámetros/ruta de instalación. El binario compilado en host fue montado sin árbol de datos de Tvheadend, lo que hace esa hipótesis prioritaria. La salida HTTP/HTSP indica intento de puesta en escucha, pero no funcionamiento sostenido; ambos puertos quedaron inaccesibles tras aborto. No atribuir a parche G3-AL sin evidencia.

Hay precedentes upstream del mismo mensaje al ejecutar Tvheadend compilado sin instalación/ajuste adecuado de datos, pero eso tampoco identifica el archivo ausente en este build: https://tvheadend.org/d/4492-manual-building-deb-packages-on-clean-ubuntu-or-other-debian-distros?page=4 .

Siguiente gate **solo lectura del checkout original**: identificar rutas de data/manifest real de configuración desde `.config.mk`, `Makefile` y `src/profile.c`, sin ejecutar `make install`, sin copiar perfiles del G3-AB original, sin reiniciar ni eliminar contenedores. Después se diseñará un montaje RO de datos o una inicialización legítima aislada.

```text
G3AM_ABORT_SIGNAL=6_CONFIRMED
G3AM_MISSING_DEFAULT_STREAM_PROFILE=OBSERVED
G3AM_ROOT_CAUSE_DATA_PATH=HYPOTHESIS_UNVERIFIED
G3AM_TVH_HTTP_HTSP=NOT_RUNNING_AFTER_ABORT
G3AM_ORIGINAL_G3AB=NOT_CHANGED_BY_DIAGNOSIS
```

## G3-AM — auditoría fuente upstream exacta de perfiles (21/11/2026)

Salida operador del checkout `8837853a6`: `.config.mk` define `prefix=/usr/local`, `datadir=${prefix}/share`; `src/profile.c:2910-2915` hace `profile_find_by_name2("pass", NULL, 1)` y `tvhabort` si no existe; `Makefile:651` declara `BUNDLES-yes += data/conf`. El operador verificó `data/conf` presente y `data/conf/profile` ausente. **La ausencia de data/conf/profile NO es prueba de falta de datos:** upstream `8837853a6` contiene `data/conf/profiles` (plural), con perfiles predefinidos `pass`, `matroska`, `htsp`. Verificado también en upstream exacto: `profile_init` intenta `hts_settings_load("profiles")`; `src/settings.c` consulta configuración local y, si no existe, ruta bundle `data/conf`. Referencias: https://raw.githubusercontent.com/tvheadend/tvheadend/8837853a6/src/profile.c , https://raw.githubusercontent.com/tvheadend/tvheadend/8837853a6/src/settings.c , https://raw.githubusercontent.com/tvheadend/tvheadend/8837853a6/data/conf/profiles .

**Hipótesis comprobable, todavía no cerrada:** el build reducido no incluyó bundle `data/conf` o no lo encuentra el runtime en `/tmp`. Siguiente gate solo lectura: revisar en el checkout `CONFIG_BUNDLE`, `ENABLE_BUNDLE` y el archivo `build.linux/bundle.c`/símbolos, la presencia local `data/conf/profiles`, y hacer inspección de `fb_stat` en `src/filebundle.c`. No recompilar, no montar perfiles improvisados, no reiniciar TVH hasta precisar si se trata de bundle deshabilitado o ubicación de datos. La solución final debe seguir la lógica de bootstrap de esta revisión, no copiar configuración del original ni modificar código de canal.

```text
G3AM_PROFILE_PASS_DEFAULT_SOURCE=VERIFIED_UPSTREAM
G3AM_DATA_CONF_PROFILES_PLURAL=VERIFIED_UPSTREAM
G3AM_CONFIG_BUNDLE=NOT_YET_VERIFIED
G3AM_PROFILE_ABORT_CAUSE=BUNDLE_OR_DATA_LOAD_HYPOTHESIS
G3AM_TVH_BOOT=FAIL_EXIT_134
```

## G3-AM — CONFIG_BUNDLE=no confirmado; bootstrap mínimo por montaje RO (21/11/2026)

Operador, auditoría local `8837853a6`:
```text
CONFIG_BUNDLE=no
data/conf/profiles=PRESENT
SHA256(data/conf/profiles)=8ef2420d92cf67b1b50959438e7850462282cccfae760f41803023788e758121
build.linux/bundle.c=MISSING
build.linux/bundle.o=MISSING
```

Causa del aborto **suficientemente identificada para un ensayo específico**: sin bundle embebido, `profile_init` necesita cargar los perfiles de `data/conf/profiles`; en `src/settings.c:326-343`, si falta configuración `/config/profiles`, la ruta de fallback es **relativa** `data/conf/profiles`. La imagen G3-AM define `WORKDIR /tmp` y antes carecía de montaje `/tmp/data/conf`. Código upstream `src/filebundle.c` admite buscar archivos físicos. Dado esto, se modifica **solo** `lab/pvr_g3ab/g3am/compose.yaml` con `/home/ubuntu/tvheadend-g3al-upstream/data/conf:/tmp/data/conf:ro`. No hay recompilación, ni copia de configuración original, ni cambio del addon ni G3-AL.

**Próximo gate**: actualizar develop en Ubuntu; verificar checksum y existencia de perfiles y `docker compose config --quiet`; ejecutar `docker compose -f g3am/compose.yaml up -d --no-deps tvh` (recrea solo el TVH experimental si cambió montaje, sin reiniciar nginx, G3-AB ni ejecutar `prepare.py`). Releer estado y HTTP/HTSP. Si no arranca, conservar logs y exit code; no asegurar PASS sin evidencia. La configuración G3-AM puede persistir y ser modificada por TVH al primer arranque; el volumen privado está separado por diseño.

```text
G3AM_CONFIG_BUNDLE=NO_CONFIRMED
G3AM_DEFAULT_PROFILE_SOURCE=VERIFIED
G3AM_DEFAULT_PROFILE_SHA256=8ef2420d92cf67b1b50959438e7850462282cccfae760f41803023788e758121
G3AM_PROFILE_FALLBACK_RELATIVE_PATH=SOURCE_VERIFIED
G3AM_COMPOSE_DEFAULT_PROFILES_RO_MOUNT=COMMITTED
G3AM_TVH_BOOT_AFTER_FIX=NOT_TESTED
```

## G3-AM — recheck tras montaje de perfiles: inicio parcial (operador, 21/11/2026)

Salida operador:
```text
G3AM_PROFILES_HASH=PASS
docker compose config --quiet=SUCCESS (sin texto de error)
docker compose up -d --no-deps tvh=STARTED
G3AM_PLAYLIST=Up 4 minutes
G3AM_TVH=Up Less than a second
PORT_29991=published_loopback
PORT_29992=published_loopback
curl: (52) Empty reply from server
G3AM_HTTP_CODE=000
G3AM_HTSP_TCP=PASS
G3AM_BOOT_RECHECK=COMPLETED
```

`G3AM_TVH=Up Less than a second` es observación en un instante inmediatamente posterior a crear contenedor, **no** uptime sostenido ni prueba de servicio estable. La conexión HTSP fue solo TCP; no se intercambió un frame HTSP. En HTTP, error 52 significa conexión cerrada sin respuesta válida: es compatible con inicialización en curso u otra falla, no permite atribuir causa. Se confirma que el nuevo volumen RO con perfiles pasó verificación de integridad, pero no declarar el aborto definitivamente corregido hasta ver estado mantenido y API HTTP.

Siguiente gate lectura tras intervalo natural sin restart: `docker compose -f g3am/compose.yaml ps -a`, estado/exit/restart count, `curl` separado a `/api/serverinfo` con control de errores, conexión HTSP TCP si sigue vivo, y clasificación de logs TVH sin exponer URLs/tokens. Si no responde, investigar logs y status antes de alterar datos.

```text
G3AM_PROFILE_MOUNT_HASH=PASS
G3AM_TVH_START_COMMAND=PASS
G3AM_HTTP_INITIAL_PROBE=FAIL_EMPTY_REPLY_52
G3AM_HTSP_TCP_INITIAL_PROBE=PASS
G3AM_TVH_STABLE_RUNTIME=NOT_VERIFIED
G3AM_HTSP_PROTOCOL=NOT_TESTED
G3AM_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — perfiles locales ausentes y error del diagnóstico Compose (21/11/2026)

Operador:
```text
CONFIG_profiles=ABSENT
CONFIG_profile=ABSENT
Mount /opt/g3al/tvheadend RW=false
Mount /tmp/data/conf RW=false
Mount /config RW=true
docker compose run --network none => unknown flag: --network
G3AM_PROFILE_VISIBILITY=COMPLETED
```

Los mounts reportados como `RO=false` provenían de plantilla `RO={{.RW}}`; **son de solo lectura** (`RW=false`). La ausencia de `profiles` y `profile` locales elimina un posible override local como causa inmediata. **Error propio del script:** Compose `run` no admite `--network` en el entorno 2.40.3; la lectura del perfil dentro del contenedor **nunca se ejecutó**, y el marcador `COMPLETED` era incondicional. No declararla PASS. Corregir usando `docker run --network none --entrypoint /bin/sh` sobre imagen `masqelec/tvh-g3am-runtime:noble` con montaje explícito del origen `/home/ubuntu/tvheadend-g3al-upstream/data/conf` a `/tmp/data/conf:ro`, usuario 1000 y comando de solo lectura; comprobar `test -r`, sha256 y JSON de perfiles. Alternativamente Compose run sin --network para verificar solo visibilidad, pero conectaría brevemente a la red compartida: preferir Docker run con network none.

```text
G3AM_CONFIG_PROFILES_OVERRIDE=ABSENT
G3AM_PROFILE_MOUNT_RW=FALSE
G3AM_PROFILE_VISIBILITY=NOT_TESTED_BAD_DIAGNOSTIC_COMMAND
G3AM_TVH_BOOT=FAIL_EXIT_134
```

## G3-AM — archivo profiles legible, aún no prueba carga interna (operador, 21/11/2026)

El operador ejecutó `docker run --network none --user 1000:1000 --read-only` sobre el runtime, con montaje explícito de `data/conf` en `/tmp/data/conf`; observó:
```text
WORKDIR=/tmp
G3AM_PROFILE_FILE=READABLE
SHA256(/tmp/data/conf/profiles)=8ef2420d92cf67b1b50959438e7850462282cccfae760f41803023788e758121
G3AM_PROFILE_VISIBILITY=PASS
```

La prueba demuestra accesibilidad del archivo montado en un contenedor auxiliar del mismo tipo, sin demostrar que `hts_settings_load("profiles")` lo haya localizado o interpretado durante el arranque fallido. Con código exacto `8837853a6`, `src/settings.c:326-343` intenta primero `/config/profiles` y luego `data/conf/profiles`; `src/filebundle.c:133-175` resuelve paths relativos mediante `tvheadend_cwd` y `TVHEADEND_DATADIR` (**no usar el shell pwd como prueba de tvheadend_cwd**). `src/profile.c:2851-2877` carga perfiles y busca `pass`. El siguiente diagnóstico es identificar **dónde se establece tvheadend_cwd** y el valor compilado de `TVHEADEND_DATADIR` sin arrancar servidor; confirmar el mapeo del bind montado en el contenedor fallido, no asumir que coincide con la prueba Docker auxiliar.

```text
G3AM_PROFILE_FILE_READABLE_IN_AUX_CONTAINER=PASS
G3AM_PROFILE_INTERNAL_LOAD=NOT_PROVEN
G3AM_TVH_BOOT=FAIL_EXIT_134
```

## G3-AM — causa raíz de ruta de perfiles y corrección en Compose (21/11/2026)

Auditoría operador del mismo checkout `8837853a6`:
```text
src/main.c:982 tvheadend_cwd0 = dirname(tvh_strdupa(argv[0]));
src/main.c:983 tvheadend_cwd = dirname(tvh_strdupa(tvheadend_cwd0));
build.linux/build.h:177 #define TVHEADEND_DATADIR "/usr/local/share/tvheadend"
CONFIG_BUNDLE=no
```

Con ejecutable invocado en `/opt/g3al/tvheadend`, el directorio base calculado es `/opt` (el argumento exacto lo aporta Docker ENTRYPOINT). `filebundle.c` busca `data/conf/profiles` bajo ese directorio o bajo `TVHEADEND_DATADIR`. La ruta previa `/tmp/data/conf` no coincide. El archivo sí era legible en un contenedor auxiliar, lo que no probaba que Tvheadend lo buscara allí. Por tanto, se actualizó exclusivamente `g3am/compose.yaml` de montaje `/tmp/data/conf:ro` a `/opt/data/conf:ro`, conservando fuente original exacta y solo lectura. No se tocó `../compose.yaml`, el binario parcheado, la configuración ni Kodi G3-AB.

**Próximo gate**: sincronizar `develop`, `docker compose -f g3am/compose.yaml config --quiet`, comprobar que el volumen se proyecta en `/opt/data/conf`, y ejecutar un contenedor efímero sin servidor para leer `/opt/data/conf/profiles` como UID 1000; después `up -d --no-deps tvh` únicamente en G3-AM, esperar breve intervalo y verificar estado continuado, GET `/api/serverinfo` HTTP (200/401/403 son respuestas HTTP válidas), y ningún SIGABRT en logs de *esa ejecución*. No confundir mensajes anteriores en logs acumulados con los nuevos. La mera compilación o comprobación de mount no es `BOOT_PASS`. Mantener NGinx/playlist G3-AM y G3-AB intactos.

```text
G3AM_TVH_CWD_CALCULATION=SOURCE_VERIFIED_/opt
G3AM_COMPILED_DATADIR=/usr/local/share/tvheadend
G3AM_PREVIOUS_MOUNT_PATH=WRONG_/tmp/data/conf
G3AM_COMPOSE_PROFILE_MOUNT_CORRECTED=/opt/data/conf:ro
G3AM_POST_CORRECTION_BOOT=NOT_TESTED
```

## G3-AM — primer arranque estable observado y API autenticada (operador, 21/11/2026)

Salida operador con montaje corregido `/opt/data/conf:ro`:
```text
docker compose -f g3am/compose.yaml config --quiet=PASS
G3AM_PLAYLIST=Up 11 minutes
G3AM_TVH=Up 5 seconds
G3AM_TVH_STATUS=running
GET /api/serverinfo => HTTP 401 CURL_EXIT=0
STATUS=running EXIT=0 RESTARTS=0
G3AM_CORRECTED_BOOT_CHECK=COMPLETED
```

El montaje correcto permitió superar el SIGABRT anterior y el servidor devolvió respuesta HTTP válida `401` (autenticación requerida). Se acredita **arranque inicial y servicio HTTP activo**, no estabilidad prolongada, no autenticación HTSP, no red IPTV ni `channelUpdate`. El `401` no prueba que exista un usuario de laboratorio ya autorizado ni una red creada.

**Siguiente gate**: a) consulta read-only del uptime y de la playlist desde el interior de la red sin revelar configuración; b) configurar acceso administrativo **solo en instancia G3-AM** desde interfaz HTTP loopback, sin copiar contraseñas del G3-AB ni publicarlas en GitHub o chat; c) crear red **IPTV Automatic Network** apuntando al recurso `http://g3am-playlist/playlist.m3u` en G3-AM con `refetch_period=1`, sin modificar identidad ni datos originales. Registrar red y canal ID antes del rename; no proceder a prueba de eventos sin baseline.

```text
G3AM_BOOT_INITIAL=PASS
G3AM_HTTP_AUTH_REQUIRED=401
G3AM_RUNTIME_STABILITY_LONG=NOT_TESTED
G3AM_IPTV_NETWORK=NOT_CONFIGURED
G3AM_HTSP_PROTOCOL=NOT_TESTED
G3AM_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — verificación posterior de uptime y playlist (operador, 21/11/2026)

```text
G3AM_TVH=Up About a minute
G3AM_PLAYLIST_SERVICE=Up 12 minutes
G3AM_CHANNEL_COUNT=2
G3AM_CUID_001=True
G3AM_CUID_002=True
```

Se acredita servidor activo al minuto, lista local privada con dos EXTINF y CUIDs esperados; la prueba no acredita que TVH haya leído la lista, importado canales, que funcionen los streams, ni renombrado caliente HTSP. Se requiere configurar/red IPTV automática solo en G3-AM, validar autenticación Web/HTSP y extraer baseline real de channel UUID/service identity antes de modificaciones M3U. Original G3-AB no se ha operado en los comandos actuales; no convertirlo en prueba de su estado actual.

```text
G3AM_TVH_UPTIME_1_MINUTE=PASS
G3AM_PLAYLIST_LOCAL_TWO_CUIDS=PASS
G3AM_IPTV_NETWORK_IMPORT=NOT_TESTED
G3AM_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — 403 Forbidden tras crear superuser de ensayo (21/11/2026)

Operador comunica exclusivamente `403 Forbidden` tras instrucción de crear `runtime/g3am/tvh_config/superuser` y reiniciar instancia experimental. No hay evidencia aún de salida `G3AM_SUPERUSER_CREATED=PASS`, reinicio, archivo de credenciales efectivamente presente/cargado, nombre de usuario introducido o diferencia entre respuesta de navegador y curl. **No atribuir 403 únicamente a ACL**, ni desactivar control de acceso. La fuente de TVH `8837853a6` confirma: `access_init` carga archivo `superuser`, y `access_get` devuelve `access_full` si credenciales superuser verifican; en `http.c:1224-1228`, HTTP 403 aparece cuando hay un nombre de usuario suministrado pero el recurso es rechazado. Puede ser contraseña errónea, cuenta no cargada, caché de autenticación del navegador o permisos, entre otros. Verificación siguiente exclusivamente G3-AM y sin revelar secretos: `stat` y extracción limitada de keys/username de `superuser`, estado del contenedor, respuesta HTTP anónima y prueba HTTP autenticada de forma interactiva con `curl --basic -u g3am-admin` pidiendo contraseña por TTY (sin ponerla en la línea de comandos, no compartir verbose/headers). Si autenticada 200 mientras navegador 403, probar sesión privada; si 403 persistente, examinar fuente/config sin agregar --noacl/--firstrun. No publicar configuración privada ni password.

```text
G3AM_ADMIN_LOGIN_BROWSER=HTTP_403_USER_REPORTED
G3AM_SUPERUSER_FILE_CREATED=NOT_CONFIRMED
G3AM_HTTP_AUTHENTICATED=NOT_TESTED
G3AM_ACL_BYPASS=FORBIDDEN
```

## G3-AM — acceso sin autenticación solicitado para laboratorio sintético (21/11/2026)

El operador solicitó expresamente eliminar la autenticación para el entorno G3-AM. Tvheadend upstream exacto `8837853a6` documenta `--noacl` en `src/main.c:960-961` y `access_init` concede acceso sin controles de ACL (`src/access.c`). Se ha añadido **solo** a `lab/pvr_g3ab/g3am/compose.yaml`; ni G3-AB ni CoreELEC se cambian. Puertos host permanecen ligados a `127.0.0.1:29991,29992`; **advertencia**: el servicio dentro del contenedor usa `--bindaddr 0.0.0.0` y comparte la red `masqelec-pvr-g3ab_pvr_g3ab`, por lo que otros contenedores en ese segmento podrían acceder sin autenticación. No usar fuera del laboratorio sintético; no exponer en interfaces externas, no añadir a producción.

Nota: el archivo `runtime/g3am/tvh_config/superuser` podría contener una contraseña creada en un paso anterior. `--noacl` deja de exigir autorización pero **no borra** esa contraseña persistida; no se solicita enviarla ni subirla a GitHub. Puede retirarse con un procedimiento privado de inspección y backup, separado del cambio actual, si se confirma presente. No promover secretos al repositorio.

Prueba del operador pendiente: `git pull --ff-only origin develop`, `docker compose -f g3am/compose.yaml config --quiet`, `up -d --no-deps tvh` y confirmar HTTP `GET /api/serverinfo` sin credenciales. `--noacl` se considera configurado en GitHub pero **no desplegado ni validado** hasta que el operador informe resultados.

```text
G3AM_NOACL_SOURCE_FLAG=UPSTREAM_VERIFIED
G3AM_NOACL_COMPOSE=COMMITTED
G3AM_NOACL_RUNTIME=NOT_TESTED
G3AB_ORIGINAL_AUTH=UNCHANGED_BY_PATCH
```

## G3-AM — HTTP API 200 sin ACL, pero interfaz web en blanco (operador, 21/11/2026)

El operador confirmó `docker compose ... up -d --no-deps tvh`, ambos contenedores `Up` a 5s/19min, y `GET /api/serverinfo => G3AM_HTTP_NOAUTH=200`. La interfaz visual aparece vacía en navegador (sin captura de consola/red, **no se atribuye categóricamente la causa**).

Auditoría código fuente exacto TVH `8837853a6`:
- `CONFIG_BUNDLE=no` confirmado previamente.
- `src/main.c:982-983` determina `tvheadend_cwd=/opt` con binario `/opt/g3al/tvheadend`.
- `src/webui/webui.c:107-124` redirige raíz a `extjs.html` cuando `ENABLE_VUE_UI` deshabilitado; `webui_static_content("/static", "src/webui/static")` en línea 2901.
- `src/filebundle.c:165-169` busca rutas `src/webui/static` bajo `tvheadend_cwd` o `TVHEADEND_DATADIR`.
- Makefile declara `src/webui/static` como assets de bundle pero este build deshabilita bundle.
- G3-AM tenía montaje de perfiles `/opt/data/conf` pero no de archivos estáticos `/opt/src/webui/static`; por tanto es plausible que API funcione y la UI no cargue.

Cambio **solo** `lab/pvr_g3ab/g3am/compose.yaml`: montar `/home/ubuntu/tvheadend-g3al-upstream/src/webui/static:/opt/src/webui/static:ro`. Mantener intacto compose G3-AB, su configuración, playlists, Kodi y el parche G3-AL. No confundir API 200 con GUI PASS.

Próximo gate operador: verificar que origen `src/webui/static` es directorio real, `docker compose config --quiet`, `up -d --no-deps tvh`, esperar 5s, comprobar estado, `GET /extjs.html` y `GET /static/... ` tras identificar una ruta del HTML, con resultados HTTP y sin imprimir cuerpo HTML; recargar navegador con caché deshabilitada. `ENABLE_VUE_UI` no se ha confirmado directamente para este build; no afirmar que Vue está ausente solo por las banderas de build indicadas.

```text
G3AM_API_NOACL_HTTP=200
G3AM_GUI_BROWSER=BLANK_REPORTED
G3AM_WEB_STATIC_MOUNT=COMMITTED_NOT_APPLIED
G3AM_GUI_AFTER_FIX=NOT_TESTED
```

## G3-AM — ExtJS parcial con pestañas de administración ausentes (21/11/2026)

El operador adjuntó HTML SingleFile de `http://127.0.0.1:29991/extjs.html` a las 22:03:47 CET. El DOM generado contiene pestañas `Electronic Program Guide`, `Digital Video Recorder`, guía con tabla vacía y footer `No events to display`, pero **no** `Configuration` ni `Status`. Se había observado `GET /api/serverinfo HTTP=200` con `--noacl`. No se ha mostrado consola de JS ni prueba de permisos emitidos a cliente.

Auditoría upstream exacta `src/webui/static/app/tvheadend.js:1042-1050,1085-1107,1254+`: función `accessUpdate(o)` crea EPG y DVR, luego `Configuration` y `Status` **solo si `o.admin == true`**. También es posible una excepción JS durante la creación de Configuration después de renderizar las primeras pestañas. `src/webui/webui.c` registra ruta ExtJS y `src/webui/extjs.c` genera la plantilla HTML. El documento SingleFile guardado elimina scripts y no demuestra errores de red en el momento de carga: evitar deducir 404 o ACL sin evidencia. Próximo gate sin cambios de contenedores: inspección de consola JS en pestaña navegador G3-AM (valores no sensibles `tvheadend.accessUpdate?.admin`, `tvheadend.capabilities` disponible, `tvheadend.confpanel`/statuspanel creados) y errores de Console tras hard reload; revisar códigos HTTP de JS y `/api/config/capabilities`. Si admin=false a pesar de `--noacl`, auditar envío de `accessUpdate` por comet y autorización; si admin=true y config no existe, priorizar traza JS/fichero ausente. No tocar G3-AB.

```text
G3AM_GUI_RENDERED_PARTIALLY=YES
G3AM_GUI_EPG_DVR_TABS=YES
G3AM_GUI_CONFIG_STATUS_TABS=MISSING
G3AM_ACCESSUPDATE_ADMIN=UNKNOWN
G3AM_CLIENT_JS_EXCEPTION=UNKNOWN
```

## G3-AM — consola confirma admin=1 y construcción interrumpida (operador, 21/11/2026)

Inspección navegador en `/extjs.html`:
```text
admin: 1
capabilitiesLoaded: true
configurationCreated: false
statusCreated: false
cometConnected: true
```

En el JavaScript exacto `src/webui/static/app/tvheadend.js:1042-1050,1102-1256`, `o.admin == true` acepta `1` por igualdad no estricta. La pestaña Configuration se asigna a `tvheadend.confpanel` **al terminar** numerosas llamadas a funciones de construcción (baseconf, imgcacheconf, satipsrvconf, acleditor, networks, etc.); si una función falta o lanza excepción, pueden aparecer EPG/DVR, pero `confpanel` y `statuspanel` quedan falsos. Se descarta como explicación suficiente `admin=false` y se prioriza excepción JS en una de esas llamadas, sin conocer aún cuál. Revisión de solo lectura en consola: enumerar **typeof sin ejecutar** de los constructores invocados en dicho bloque, revisar el primer error rojo original de consola; también comprobar HTTP de asset faltante si señala URL concreta. No cambiar --noacl ni Compose hasta identificar causa. El HTML SingleFile es snapshot ya renderizado, no demuestra error JS concreto ni la secuencia de cargas de recursos.

```text
G3AM_BROWSER_ACCESSUPDATE_ADMIN=1
G3AM_BROWSER_CAPABILITIES_LOADED=TRUE
G3AM_BROWSER_CONFIG_PANEL=FALSE
G3AM_BROWSER_STATUS_PANEL=FALSE
G3AM_BROWSER_COMET_OBJECT=TRUE
G3AM_GUI_CAUSE=UNKNOWN_EXCEPTION_OR_MISSING_CONSTRUCTOR
```

## G3-AN — diagnóstico de Configuration ExtJS incompleto (21/11/2026)

Valores reales de consola navegador del operador:
```text
admin=1
capabilitiesLoaded=true
configurationCreated=false
statusCreated=false
cometConnected=true
G3AM_MISSING_METHODS=["codec_tab","caclient"]
G3AM_CAPABILITIES=["caclient","tvadapters","satip_client","satip_server","timeshift","trace"]
```

Revisión código upstream exacto `8837853a6`:
- `src/webui/static/app/tvheadend.js:1192-1193` solo invoca `codec_tab` si el servidor anuncia `libav`; el operador no tiene `libav`, por lo que la ausencia de `codec_tab` es **esperada** y no bloqueante.
- `src/webui/static/app/tvheadend.js:1214-1215` invoca `tvheadend.caclient(cp,6)` si `capabilities` incluye `caclient`. Operador: incluye `caclient` pero la función falta; esto explica de modo concreto una excepción `TypeError: tvheadend.caclient is not a function` antes de `tvheadend.confpanel=cp` (línea 1250) y antes de insertar Status (línea 1254).
- `src/main.c:157-159` anuncia `caclient` cuando `ENABLE_CWC || ENABLE_CAPMT || ENABLE_CONSTCW || ENABLE_CCCAM || ENABLE_LINUXDVB_CA`.
- `Makefile.webui:131-137` incluye `caclient.js` **solo** si `CONFIG_CWC || CONFIG_CCCAM || CONFIG_CAPMT`. Las opciones CONSTCW/LINUXDVB_CA permiten anunciar capacidad con JS omitido. Esto es defecto de compatibilidad build/webui en este upstream. Ausencia de consola de excepción exacta: la causa es una deducción fuerte de condiciones observadas, pendiente de probar reparada.

Se versiona parche incremental `lab/pvr_g3ab/patches/tvheadend-8837853a6-g3an-caclient-ui-capability.patch` que modifica **solo** la guarda del array `tvheadend_capabilities` en `src/main.c` para anunciar caclient únicamente cuando `ENABLE_CWC || ENABLE_CAPMT || ENABLE_CCCAM` (igual que la inclusión JS). No cambia backend, ACL, fuentes M3U, ni canal. Se debe comprobar `git apply --check` en checkout upstream del operador **que ya tiene parche G3-AL** y recompilar `make -j2` en el host para aplicar a binario. No reejecutar `./configure`; conservar flags configurados. Antes de compilar parar únicamente contenedor experimental G3-AM TVH y guardar copia binaria rollback fuera del proyecto versionado; levantar de nuevo con `--force-recreate` (bind mount del ejecutable, evita old inode). Nunca parar G3-AB.

Gates pendientes: `G3AN_PATCH_CHECK`, `G3AN_BUILD`, `G3AN_HTTP_API`, `G3AN_CAPABILITIES_NO_CACLIENT`, `G3AN_GUI_CONFIGURATION_STATUS`. No declarar éxito hasta output de operador.

## G3-AN — diagnóstico concreto de ExtJS incompleto y parche de compilación (operador, 22/11/2026)

Consola del operador tras reinicio de Ubuntu:
```text
G3AM_MISSING_METHODS=["codec_tab","caclient"]
G3AM_MISSING_COUNT=2
G3AM_CAPABILITIES=["caclient","tvadapters","satip_client","satip_server","timeshift","trace"]
```

Análisis fuente upstream exacta TVH `8837853a6`:
- `src/webui/static/app/tvheadend.js:1192` invoca `codec_tab` solo con capacidad `libav`, **ausente**, por tanto no es anomalía.
- `src/webui/static/app/tvheadend.js:1214-1215` invoca `tvheadend.caclient(cp,6)` cuando capability `caclient` existe; su ausencia aborta la construcción de Configuration antes de asignar `confpanel` y crear Status.
- `src/main.c:157-159` anuncia `caclient` cuando CWC/CAPMT/CONSTCW/CCCAM/**LINUXDVB_CA** estén habilitadas.
- `Makefile.webui:131-136` incluye `app/caclient.js` **solo** con CONFIG_CWC, CONFIG_CCCAM o CONFIG_CAPMT. No contempla CONSTCW ni LINUXDVB_CA.
- `src/webui/static/app/caclient.js:5` define la función que falta.
- El build lab había desactivado CWC/CAPMT/CONSTCW/CCCAM pero aparentemente sigue anunciando acceso condicional, probablemente por LINUXDVB_CA; verificar flag explícita en `.config.mk` antes de ejecutar rebuild, no afirmar qué flag exacta causa capability sin lectura de configuración.

Corrección fuente preparada en rama `develop`, archivo `lab/pvr_g3ab/patches/tvheadend-8837853a6-g3an-caclient-webui-capability.patch`: añadir `CACLIENT-$(CONFIG_CONSTCW) = yes` y `CACLIENT-$(CONFIG_LINUXDVB_CA) = yes` para alinear WebUI con los flags que usa `main.c`. No se ha aplicado al checkout host, ni recompilado ni arrancado la UI reparada. G3-AL permanece separado y no se toca; no propagar --noacl a producción.

Siguiente gate del operador: actualizar repo `develop`, inspeccionar 5 CONFIG_* de CA en `.config.mk`, `git apply --check`, `git apply` (solo Makefile.webui), parar exclusivamente G3-AM TVH antes de reconstruir el binario montado, `make -j2` en checkout upstream y validar, arrancar solo G3-AM TVH, verificar API y comprobar en consola `typeof tvheadend.caclient === "function"` y `confpanel/statuspanel`. Registrar resultado y nuevo checksum del binario para futuros arranques; el checksum histórico anterior dejará de ser válido. No ejecutar gate de renombrado hasta entonces.

```text
G3AM_MISSING_CODEC_TAB=EXPECTED_NO_LIBAV
G3AM_MISSING_CACLIENT=BUG_CONFIRMED_CAPABILITY_UI_MISMATCH
G3AN_PATCH_REPOSITORY=COMMITTED
G3AN_PATCH_HOST=NOT_APPLIED
G3AN_NEW_BINARY=NOT_BUILT
G3AM_GUI_REPAIRED=NOT_VERIFIED
```

## G3-AN — compilación completada, fallo de GUI persistente (22/11/2026)

Salida del operador:
```text
SHA256(build.linux/tvheadend)=f02a8858a0fe304b8a7fb5da78db7b4cd16dc354fad7327c4dbb49afc8bd61e5
VERSION=4.3-2897~g8837853a-dirty
G3AM_TVH=Up 5 seconds
G3AN_HTTP=200
G3AN_BUILD_AND_BOOT=COMPLETED
BROWSER typeof tvheadend.caclient=undefined
BROWSER configuration=false
BROWSER status=false
BROWSER admin=1
```

El parche G3-AN no pasó el gate de GUI. ExtensionMessagingService.js puede ser una extensión ajena, sin prueba de relación con TVH.

En Makefile.webui upstream, el artefacto src/webui/static/tvh.js.gz depende de JAVASCRIPT_SRC, pero no directamente del propio Makefile.webui. Al cambiar solo lista de fuentes por flags, Make puede reutilizar un artefacto comprimido previo si no detecta el cambio; también cabe caché navegador. Siguiente diagnóstico, sin mutaciones: revisar cinco CONFIG_* CA en .config.mk; comprobar que el Makefile.webui parcheado incluye nuevos flags; comprobar generado src/webui/static/tvh.js.gz mediante gzip -cd con Python leyendo bytes y buscando tvheadend.caclient; revisar make -n -f Makefile.webui WEBUI=std sobre target exacto. Solo después forzar regeneración dirigida del bundle JS y, si procede, volver a abrir en sesión de navegador limpia.

```text
G3AN_NEW_BINARY_SHA256=f02a8858a0fe304b8a7fb5da78db7b4cd16dc354fad7327c4dbb49afc8bd61e5
G3AN_WEBUI_CACLIENT=UNDEFINED
G3AN_GUI_CONFIG_STATUS=FALSE
G3AN_BUILD_GATE=PASS
G3AN_GUI_GATE=FAIL
G3AN_COMPRESSED_JS_REGENERATED=UNKNOWN
```

## G3-AN — bandera CA comprobada y artefacto JS posiblemente obsoleto (22/11/2026)

Datos de la auditoría del operador:
```text
CONFIG_CWC=no
CONFIG_CCCAM=no
CONFIG_CAPMT=no
CONFIG_CONSTCW=no
CONFIG_LINUXDVB_CA=yes
Makefile.webui contiene CACLIENT-$(CONFIG_LINUXDVB_CA) = yes
src/webui/static/tvh.js.gz: gzip válido, 1097516 bytes descomprimidos
b'tvheadend.caclient' in bundle=True
b'tvheadend.codec_tab' in bundle=True
make -n -f Makefile.webui WEBUI=std src/webui/static/tvh.js.gz -> ya actualizado
```

El token caclient aparece también en tvheadend.js en su llamada (sin garantizar que exista la declaración). Lo mismo ocurre con codec_tab, pese a CONFIG_LIBAV deshabilitado, por lo que la búsqueda de subcadena es insuficiente. En la versión upstream exacta, Makefile.webui regenera tvh.js.gz a partir de JAVASCRIPT_SRC; cambiar Makefile.webui solamente no fuerza la reconstrucción por depender de los .js, no del Makefile. No concluir aún si el bundle tiene la definición: usar patrón de asignación `tvheadend.caclient = function` tolerante a espacios sobre el contenido descomprimido.

Próximo gate experimental dirigido: ejecutar `make -f Makefile.webui WEBUI=std -W src/webui/static/app/caclient.js src/webui/static/tvh.js.gz` en checkout upstream (fuerza solo el artefacto JS dejando el fuente intacto); verificar con Python gzip+regex la definición, no únicamente la referencia; como el árbol src/webui/static está montado en RO en el contenedor G3-AM, verificar `GET /static/tvh.js.gz` local y forzar recarga sin caché del navegador. No reiniciar G3-AB, G3-AM ni recompilar todo hasta comprobar resultado. No alterar el SHA del binario salvo que se recompilara por separado.

```text
G3AN_LINUXDVB_CA=yes
G3AN_CACLIENT_MAKE_RULE=PATCHED
G3AN_JS_GZIP=VALID
G3AN_JS_CACLIENT_TOKEN=FOUND_NOT_PROOF_OF_DEFINITION
G3AN_JS_CACLIENT_DEFINITION=NOT_VERIFIED
G3AN_JS_TARGET=REPORTED_UP_TO_DATE
G3AN_GUI_GATE=FAIL
```

## G3-AN — Regeneración dirigida del JavaScript resuelve interfaz (22/11/2026)

Evidencia reportada por el operador después de `make -f Makefile.webui WEBUI=std -W src/webui/static/app/caclient.js src/webui/static/tvh.js.gz`:

```text
src/webui/static/tvh.js.gz.tmp=1409436
src/webui/static/tvh.js.gz.tmp2=1098767
src/webui/static/tvh.js.gz=295299
G3AN_JS_GZIP=PASS
G3AN_JS_UNCOMPRESSED_BYTES=1098767
G3AN_CACLIENT_DEFINED=True
G3AN_JS_SHA256=a4890cab8320abfcd5f5667b401219755a12b8d94311752025ebb19a724abc00
G3AN_CACLIENT_DEFINITION=PASS
G3AN_WEB_JS_HTTP=200
G3AN_WEB_JS_REBUILD=COMPLETED
OPERATOR_GUI_RESULT=ahora si
```

Conclusión: la regeneración dirigida incorporó efectivamente `tvheadend.caclient = function` al bundle. El operador confirma visualmente que la interfaz ahora funciona, pero todavía no ha entregado la prueba de consola final `configuration=true`, `status=true`; marcar confirmación visual y no afirmar ejecución automatizada del gate. Root cause: modificación de lista de fuentes en Makefile.webui no invalidaba el artefacto comprimido preexistente; una recompilación completa previa generó binario distinto sin refrescar el bundle. El montaje RO de archivos estáticos ya permite servir el bundle actualizado sin reiniciar TVH. El hash del ejecutable Linux experimental permanece según evidencia previa `f02a8858a0fe304b8a7fb5da78db7b4cd16dc354fad7327c4dbb49afc8bd61e5`; no se calculó nuevamente en este paso. Ningún cambio G3-AB ni despliegue CoreELEC.

Próxima fase: configurar *solo G3-AM* red IPTV Automatic Network con URL `http://g3am-playlist/playlist.m3u`, verificar `g3am-001` y `g3am-002`, mapear servicios y obtener identidad baseline; mantener intacto G3-AB y no ejecutar `prepare.py rename` antes de preparar observación HTSP persistente.

```text
G3AN_JS_BUNDLE_DEFINITION=PASS
G3AN_JS_HTTP=200
G3AN_GUI_VISUAL_OPERATOR=PASS
G3AN_GUI_CONSOLE_GATE=NOT_CAPTURED
G3AM_IPTV_AUTO_NETWORK=NOT_CONFIGURED
G3AM_HTSP_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — Nginx 403 al descargar M3U HTTP: defecto de modo de archivo (22/11/2026)

Operador ejecutó `docker run --rm --network masqelec-pvr-g3ab_pvr_g3ab --entrypoint wget busybox:1.36 -qO- http://g3am-playlist/playlist.m3u`: respuesta HTTP 403 Forbidden. El contenedor TVH experimental no tiene curl, lo que no implica fallo de conectividad. El comando previo mostraba `TEST FINISHED` incluso tras fallo de wget por falta de `set -e`; futuras pruebas deben abortar ante HTTP 403.

Auditoría del código privado `g3am/prepare.py`: `tempfile.mkstemp()` crea temporal con permisos 0600; `os.replace(temp,target)` conserva esos permisos y no hay chmod. nginx:alpine sirve volumen privado `../runtime/g3am/playlist:/usr/share/nginx/html:ro`, normalmente con usuario trabajador distinto del dueño de host, lo que hace probable HTTP 403 por acceso denegado. Aún no se confirmó el modo real del archivo ni permisos de carpetas en host ni log de nginx. Se corrigió el generador para ejecutar `os.fchmod(fd,0o644)` antes de escribir/reemplazar; afecta solamente al archivo M3U sintético (contenido no secreto) y no a configuración TVH. **No ejecutar `prepare.py baseline` o `rename` para reparar el permiso**, porque se alteraría el estado de prueba de la playlist; usar ajuste de permisos puntual del archivo existente, después de verificar marca sintética, ruta real, propietario y rechazo de symlinks. Diagnóstico adicional: `stat` de directorios y archivo, `docker logs --tail 20 masqelec-pvr-g3am-playlist-1`, y reintento HTTP con `wget` que detenga la ejecución si falla. Prohibido modificar G3-AB.

```text
G3AM_HTTP_PLAYLIST=403_OPERATOR
G3AM_PREPARE_MKSTEMP_0600_BUG=CONFIRMED_BY_SOURCE
G3AM_PREPARE_FCHMOD_0644_PATCH=COMMITTED
G3AM_EXISTING_PLAYLIST_PERMISSIONS=UNKNOWN
G3AM_HTTP_PLAYLIST_AFTER_FIX=NOT_TESTED
```

## G3-AM — HTTP M3U reparado y verificado (22/11/2026)

El operador ejecutó la reparación acotada al archivo `runtime/g3am/playlist/playlist.m3u` con marca sintética y validación de propietario/symlinks. Evidencia:

```text
G3AM_MODE_BEFORE=0o600
G3AM_MODE_AFTER=0o644
G3AM_PERMISSIONS_REPAIRED=PASS
#EXTM3U
#EXTINF:-1 CUID="g3am-001" tvg-chno="1" tvh-chnum="1" tvg-name="G3AM Alpha" group-title="G3AM SYNTHETIC",G3AM Alpha
http://streams/ch1.ts
#EXTINF:-1 CUID="g3am-002" tvg-chno="2" tvh-chnum="2" tvg-name="G3AM Beta" group-title="G3AM SYNTHETIC",G3AM Beta
http://streams/ch2.ts
G3AM_PLAYLIST_HTTP=PASS
```

**Diagnóstico confirmado:** archivo previo creado 0600 por `tempfile.mkstemp()` impedía lectura del worker nginx; chmod 0644 en el archivo existente eliminó HTTP 403. El generador ya quedó corregido con `os.fchmod(fd, 0o644)` para próximas publicaciones. El contenido HTTP mantiene exactamente dos CUID y los nombres baseline, sin ejecutar rename. No se prueba con esto importación IPTV de Tvheadend, mapeado a canales ni propagación de `channelUpdate` a HTSP.

Próximo gate: configurar exclusivamente en la web G3-AM puerto 29991 una red `IPTV Automatic Network` con URL HTTP interna `http://g3am-playlist/playlist.m3u`, revisar los Muxes/Services y el mapeado de canales, registrar identidades originales antes de cambiar el nombre. No ejecutar `prepare.py rename` hasta que esté preparada la captura HTSP persistente; mantener intacto el entorno G3-AB y su configuración.

```text
G3AM_PLAYLIST_FILE_MODE=0644
G3AM_PLAYLIST_HTTP=PASS
G3AM_PLAYLIST_CHANNEL_COUNT=2
G3AM_PLAYLIST_BASELINE_CUIDS=PASS
G3AM_IPTV_NETWORK=NOT_YET_CONFIRMED
G3AM_HTSP_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — IPTV no importada: única red deshabilitada (22/11/2026)

Evidencia de API suministrada por el operador:

```text
NETWORKS HTTP=200 COUNT=1 TOTAL=1
uuid=cc090ea0e9bf9e8670520252e4c23306
networkname=IPTV LOCAL
enabled=false
url=?
MUXES HTTP=200 COUNT=0 TOTAL=0
SERVICES HTTP=200 COUNT=0 TOTAL=0
CHANNELS HTTP=200 COUNT=0 TOTAL=0
```

La causa inmediata comprobada de ausencia de descarga/importación es que la única red IPTV está deshabilitada; `url=?` requiere confirmar el valor real (podría ser presentación de la API). La URL HTTP de nginx ya funciona y contiene CUID g3am-001/g3am-002. Los errores observados de `/static/icons/*.png` y `/static/extjs/resources/images/*` devuelven HTTP 500 y son otro defecto de recursos web, independiente de la red deshabilitada. No se han creado muxes ni servicios, así que no hay todavía identidades persistentes a comparar. Próximo paso: lectura acotada `GET /api/idnode/load?uuid=cc090ea0e9bf9e8670520252e4c23306` para recoger campos *no secretos* `enabled`, `url`, tipo/clase, `refetch_period`, `scan_create`, y contrastar con lista de red. No imprimir JSON completo porque puede contener contraseñas o parámetros de autenticación. Luego habilitar solo red G3-AM y corregir URL si hace falta; comprobar muxes antes de mapeo. No ejecutar `prepare.py rename`, no tocar G3-AB.

```text
G3AM_IPTV_NETWORK_COUNT=1
G3AM_IPTV_NETWORK_ENABLED=FALSE
G3AM_IPTV_NETWORK_URL=UNVERIFIED_QUESTION_MARK
G3AM_MUXES=0
G3AM_SERVICES=0
G3AM_CHANNELS=0
G3AM_STATIC_ICON_HTTP_500=OBSERVED
G3AM_G3AL_HTSP_RENAME=NOT_TESTED
```

## G3-AM — Detalle de la red existente: URL incorrecta (22/11/2026)

Salida del operador de `GET /api/idnode/load?uuid=cc090ea0e9bf9e8670520252e4c23306`, analizando `params` como lista:

```text
G3AM_NETWORK_CLASS=iptv_auto_network
G3AM_FIELDS_FORMAT=list
enabled=True
networkname=IPTV LOCAL
refetch_period=1
scan_create=True
url_is_expected=False
```

Observación crítica: la API grid anterior indicaba `enabled=false` mientras que el detalle más reciente indica `enabled=True`. El campo URL no coincide con `http://g3am-playlist/playlist.m3u`; no se conoce el valor real porque la consulta evita imprimir potenciales credenciales. Ya hay una red, no crear duplicados. Instrucción operador: editar únicamente `IPTV LOCAL` en GUI, fijar URL interna exacta HTTP, confirmar Enabled y refetch 1, guardar, después volver a medir URL y COUNT de networks/muxes/services/channels por API. No ejecutar prepare.py rename, no tocar G3-AB. Pendiente validar importación, mapeo, identidad y eventos HTSP. Esto es un diagnóstico de configuración, no una prueba de que el parser o parche G3-AL falle.

```text
G3AM_IPTV_NETWORK_CLASS=iptv_auto_network
G3AM_IPTV_ENABLED_DETAIL=True
G3AM_IPTV_URL_MATCH=False
G3AM_IPTV_REFETCH_MINUTES=1
G3AM_IPTV_SCAN_CREATE=True
G3AM_IPTV_URL_FIXED=NOT_CONFIRMED
```

## G3-AM — M3U importada; 2 muxes, 3 servicios, sin canales (22/11/2026)

Resultado del operador después de corregir URL de `IPTV LOCAL`:

```text
G3AM_URL_OK=True
G3AM_ENABLED=True
G3AM_NETWORKS=1
G3AM_MUXES=2
G3AM_SERVICES=3
G3AM_CHANNELS=0
```

La descarga y el parseo de la M3U HTTP ya crean exactamente 2 muxes, pero el escaneo detectó 3 servicios. Los 3 servicios no deben mapearse indiscriminadamente: un mux TS puede anunciar varios programas, o podrían existir entradas adicionales que requieren investigar. Ninguna identidad de canal está aún establecida. Próximo gate: obtener en solo lectura `api/mpegts/mux/grid` y `api/mpegts/service/grid` con `all=1`, imprimiendo únicamente campos no sensibles (`uuid`, `name`, `mux`, `network`, `sid`, `scan_result`, `scan_state`, `enabled`, `channel`, `channelname`, `servicename`, `svcname`, `provider`, `type`, `pmt`) y listar nombres de campos disponibles si hace falta. Correlacionar servicios por mux y mapear de manera selectiva solo los dos servicios pertinentes. Mantener intocados G3-AB, lista baseline y CUID; no ejecutar `prepare.py rename` hasta guardar UUID del canal y preparar observador HTSP persistente.

```text
G3AM_IPTV_HTTP_MUX_IMPORT=PASS
G3AM_IPTV_MUX_COUNT=2
G3AM_IPTV_SERVICE_COUNT=3
G3AM_IPTV_CHANNEL_COUNT=0
G3AM_SERVICE_TO_MUX_ASSOCIATION=NOT_YET_VERIFIED
G3AM_HTSP_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — identificación de 3 servicios en 2 muxes, mapeo selectivo pendiente (22/11/2026)

El operador proporcionó inventario API y exportación SingleFile de la pestaña Services a las 00:20:15 CET. El DOM de la UI incluye las pestañas Configuration/Status (reparación ExtJS confirmada), el selector "Hide: Inactive services", los servicios y botón "Map Selected"; la fila deshabilitada está visible/seleccionada en la captura.

Servicios:
- Mux `playlist.m3u - G3AM Alpha`: `66f63f4e1a9d19a643a806990433bb8c`, SID 1, enabled=true, `svcname=G3AB Signal 1` (provider FFmpeg), sin canales.
- Mux `playlist.m3u - G3AM Beta`: `68a79db48e632d6a766b7eee25d97458`, SID 2, enabled=true, `svcname=G3AB Signal 2` (provider FFmpeg), sin canales.
- Mux Beta: `949dba9313a31b88edc8b1263fba9869`, SID 1, `svcname=G3AM Beta`, enabled=false, indicador UI `Missing In PAT/SDT`, sin canales.

La tercera entrada parece ser el servicio nominal provisional del M3U sustituido tras escanear el programa MPEG-TS real; confirmada la condición inactiva/missing, no eliminarla ni mapearla por defecto. Para tener exactamente 2 canales: seleccionar exclusivamente los dos servicios habilitados (identificar por UUID/SID/nombre/mux), usar Map Selected y validar `channel/grid` y asociaciones `mpegts/service/grid`. Evitar la fila Beta SID1. El mapper puede crear canales con nombres `G3AB Signal 1/2`, distintos de `G3AM Alpha/Beta`. Esto tiene **impacto directo** en el gate G3-AL: el parche solo emite htsp_channel_update si el nombre *efectivo de un canal autoname* cambia después de la variación `im->mm_iptv_svcname`; una variación de M3U sin cambio del nombre efectivo derivado de un servicio real puede resultar en 0 notificaciones legítimamente. Registrar ch_name/ch_autoname y nombre efectivo de ambos canales antes de rename; no forzar nombres manuales ni dar por probada la solución.

```text
G3AM_SERVICE_ALPHA_UUID=66f63f4e1a9d19a643a806990433bb8c
G3AM_SERVICE_BETA_UUID=68a79db48e632d6a766b7eee25d97458
G3AM_SERVICE_BETA_PROVISIONAL_UUID=949dba9313a31b88edc8b1263fba9869
G3AM_BETA_PROVISIONAL_STATE=DISABLED_MISSING_IN_PAT_SDT
G3AM_ACTIVE_SERVICES=2
G3AM_CHANNEL_MAPPING=NOT_YET_EXECUTED
G3AL_RENAME_EFFECTIVE_NAME_BEHAVIOR=UNVERIFIED
```

## G3-AM — mapeo sin efecto tras inventario (22/11/2026)

El operador volvió a ejecutar el baseline: CHANNEL_COUNT=0 y todas las listas `channel` de servicios vacías (Signal 1 SID1 enabled, Signal 2 SID2 enabled, Beta provisional SID1 disabled). El botón `Map Selected` de ExtJS no mapea inmediatamente: upstream `src/webui/static/app/servicemapper.js:96-127` abre ventana `Map services to channels`, selecciona UUID y solo el botón de guardado `Map services` ejecuta `api/service/mapper/save`; luego cambia a pestaña de seguimiento `service_mapper`. API dispone de endpoint `api/service/mapper/status` (`src/api/api_service.c`) con contadores total/ok/fail/ignore y opcional active. Si se usó la ventana y guardado realmente, la causa todavía desconocida; hay que comprobar status/errores de `service_mapper`, especialmente opción `Check availability`. No borrar ni mapear el servicio inactivo, ni ejecutar rename. Hay evidencia adicional en parche G3-AL: solo se notifica a canales ch_autoname cuyo nombre efectivo cambia, lo que puede no suceder si se usan nombres internos G3AB Signal 1/2; gate HTSP necesita evaluar nombre efectivo antes del renombrado.

```text
G3AM_CHANNEL_COUNT=0
G3AM_ACTIVE_SERVICE_CHANNEL_LINKS=EMPTY
G3AM_MAPPER_SAVE_CONFIRMED=NO
G3AM_MAPPER_STATUS=UNKNOWN
```

## G3-AM — mapper 0/0/0/0, propuesta API controlada (22/11/2026)

El operador midió `api/service/mapper/status` -> `{total:0,ok:0,fail:0,ignore:0}` y `api/channel/grid?all=1` -> 0. Esto **no prueba** si el POST fue enviado ni la causa de falta de actividad. Código upstream verificado: `servicemapper.js` `Map Selected` abre diálogo y guarda vía `api/service/mapper/save`; `src/api/api_service.c` enruta a `api_idnode_save_simple`; `src/api/api_idnode.c` exige parámetro POST `node` tipo mapa; `src/service_mapper.c` guarda lista `services`, y en `ic_save` inicia `service_mapper_start()` si no está vacía. `service_mapper_start` filtra por UUID, omite servicio ya mapeado, deshabilitado, no-tv/no-radio o cifrado (si no está habilitado). La opción `check_availability=false` permite proceso síncrono.

Siguiente ensayo propuesto (todavía NO ejecutado): operador ejecuta Python local contra puerto 29991, preflight de network/mux/service/channel y UUIDs, POST a mapper/save con exactamente los UUID activos Signal 1/Signal 2, sin Beta provisional; `node` JSON con `services` y `check_availability:false`, leer estadísticas y canales y parar si no se cumplen gates; sin tocar G3-AB. Mantener baseline de playlist, sin rename.

```text
G3AM_MAPPER_STATUS_TOTAL=0
G3AM_MAPPER_STATUS_OK=0
G3AM_MAPPER_STATUS_FAIL=0
G3AM_MAPPER_STATUS_IGNORE=0
G3AM_CHANNELS=0
G3AM_DIRECT_API_MAPPER=NOT_EXECUTED
```

## G3-AM — dos canales auto-name creados (22/11/2026)

El operador comunica que 'bucket' está desactivado (posiblemente se refiere a Bouquets; terminología no confirmada). Segunda ejecución de lectura API confirma:

```text
MAPPER={"total":0,"ok":0,"fail":0,"ignore":0}
CHANNELS COUNT=2
uuid=2591ccd729867bffc24e8f4bd8b765af name=G3AM Beta number=2 autoname=True
uuid=beec46e5ab595d2474289e74c9ab9849 name=G3AM Alpha number=1 autoname=True
```

**Gate de baseline de canal superado:** exactamente 2 canales con numeración/nombres M3U esperados y autoname habilitado. Las estadísticas de mapper en 0 no explican quién los creó: no atribuir causalidad al mapeo por API o a bouquets sin evidencia. Necesario confirmar servicio→canal por lectura API y obtener detalle `api/idnode/load` de los canales, especialmente ch_name explícito y flags de auto-name. No ejecutar `prepare.py rename` hasta iniciar observación HTSP persistente: registrar uuid, nombre, número, asociaciones antes/después y eventos `channelUpdate`; `channelDelete` y `channelAdd` no deben ocurrir. Preservar G3-AB intacto. No reactivar Bouquets si están desactivados en lab.

```text
G3AM_CHANNEL_BASELINE=PASS
G3AM_CHANNEL_COUNT=2
G3AM_ALPHA_UUID=beec46e5ab595d2474289e74c9ab9849
G3AM_BETA_UUID=2591ccd729867bffc24e8f4bd8b765af
G3AM_BOTH_CHANNELS_AUTONAME=True
G3AM_HTSP_CHANNELUPDATE=NOT_TESTED
```

## G3-AM — gate HTSP persistente preparado (22/11/2026)

Operador confirmó asociación real por API:

```text
G3AM Alpha: ch UUID beec46e5ab595d2474289e74c9ab9849; number=1; autoname=True
  service G3AB Signal 1 SID1 -> channel [beec46e5ab595d2474289e74c9ab9849]
G3AM Beta: ch UUID 2591ccd729867bffc24e8f4bd8b765af; number=2; autoname=True
  service G3AB Signal 2 SID2 -> channel [2591ccd729867bffc24e8f4bd8b765af]
G3AM Beta provisional SID1: enabled=False, channel=[]
```

Herramienta `tools/pvr_g3am_htsp_watch.py` versionada: conexión exclusiva `127.0.0.1:29992`, hello HTSP y enableAsyncMetadata, eventos channelAdd/channelUpdate/channelDelete/initialSyncCompleted, sin autenticación por --noacl de laboratorio y sin reproducción. Ejecutar desde Ubuntu en **terminal 1**: `python3 service.cloud.masqelec/tools/pvr_g3am_htsp_watch.py --seconds 180`; esperar `G3AM_HTSP_READY_FOR_RENAME=YES`, sin cerrar conexión. En **terminal 2**, tras verificar ruta, marca sintética y estado baseline, ejecutar `python3 service.cloud.masqelec/lab/pvr_g3ab/g3am/prepare.py rename`. La lista HTTP se volverá a publicar y refetch=1 minuto; NO reiniciar TVH durante prueba. Observar `channelUpdate` con Alpha Renamed, 0 channelAdd/Deletes después de initialSync, UUID TVH idénticos y Beta intacta. Diferenciar ID HTSP de UUID TVH y de ID Kodi. El observador es candidato aún no ejecutado en Ubuntu; su éxito no demuestra comportamiento Kodi. Futuro gate: Kodi G3-AM con perfil completamente separado de `runtime/kodi_home/.kodi`, no reutilizar proceso G3-AB ni PVR DB. No afirmar gate hasta disponer de evidencias.

```text
G3AM_SERVICE_ASSOCIATIONS=PASS
G3AM_TWO_CHANNEL_BASELINE=PASS
G3AM_HTSP_OBSERVER_COMMITTED=YES
G3AM_HTSP_RENAME=NOT_TESTED
G3AM_KODI_INTEGRATION=NOT_TESTED
```

## G3-AM — evidencia runtime positiva de channelUpdate en HTSP persistente (22/11/2026)

El operador abrió `tools/pvr_g3am_htsp_watch.py` y confirmó `G3AM_HTSP_CONNECTED=YES`, `G3AM_HTSP_INITIAL_SYNC=PASS`, `G3AM_HTSP_READY_FOR_RENAME=YES`. Inicialmente llegaron `channelAdd` con IDs HTSP Beta `1473024293`, Alpha `1699146942`. Con la conexión abierta ejecutó `g3am/prepare.py rename`, que imprimió `G3AM_STAGE=RENAME`, playlist PRIVATE_ONLY y G3AB original untouched. El observador recibió:

```text
HTSP_EVENT=channelUpdate ID=1699146942 NAME=G3AM Alpha Renamed PHASE=AFTER_SYNC
```

**Interpretación:** el parche G3-AL en runtime emite al menos un `channelUpdate` de Alpha con el **mismo channelId HTSP** que la sincronización inicial, sin reconexión del observador. Esta evidencia supera el gate de notificación en conexión persistente. Todavía no se ha recibido salida final del observador (`G3AM_HTSP_SUMMARY`), ni snapshot API post-rename demostrando UUID TVH constante y Beta intacta, ni comparación de eventos sin add/delete posteriores al initialSync. No afirmar gate completo de identidad ni éxito en Kodi.

Próximo gate: API `/api/channel/grid?all=1` con conjunto exacto de UUID Alpha `beec46e5ab595d2474289e74c9ab9849`, Beta `2591ccd729867bffc24e8f4bd8b765af`, nombres Alpha Renamed/Beta y contadores finales HTSP. Luego preparar Kodi G3-AM con **nuevo perfil y directorio de datos** distintos de `runtime/kodi_home/.kodi` de G3-AB; evaluar capacidad de lanzamiento sin colisión de Kodi/puertos antes de cambios. Cuidar que el rename ya sucedió: para ensayo Kodi repetir ciclos baseline->rename con observación activa y capturar PVR.GetChannels antes/después.

```text
G3AM_PERSISTENT_HTSP_CHANNELUPDATE=PASS
G3AM_ALPHA_HTSP_ID_INITIAL=1699146942
G3AM_ALPHA_HTSP_ID_UPDATE=1699146942
G3AM_ALPHA_HTSP_NAME_AFTER=G3AM Alpha Renamed
G3AM_TVH_PERSISTENT_UUID_POST_RENAME=NOT_YET_VERIFIED
G3AM_HTSP_POST_SYNC_NO_CHURN=NOT_YET_VERIFIED
G3AM_KODI_PVR_SYNC=NOT_TESTED
```

## G3-AM — UUID persistente tras rename PASS (22/11/2026)

Operador validó `GET /api/channel/grid?all=1` después de publicar `G3AM_STAGE=RENAME` y recibir `channelUpdate` en la misma conexión HTSP. Resultado:

```text
CHANNEL=G3AM Alpha Renamed RESULT=PASS
UUID=beec46e5ab595d2474289e74c9ab9849 ACTUAL_NAME=G3AM Alpha Renamed
CHANNEL=G3AM Beta RESULT=PASS
UUID=2591ccd729867bffc24e8f4bd8b765af ACTUAL_NAME=G3AM Beta
G3AM_RENAME_IDENTITY=PASS
```

La validación también comprobó que son exactamente 2 UUID conocidos, los nombres esperados, números 1/2 y autoname=True. Separadamente, HTSP entregó `channelUpdate` de Alpha con ID HTSP persistente `1699146942`. No constan todavía los contadores del cierre del observador para descartar todos los eventos `channelAdd` y `channelDelete` posteriores a INITIAL. **Gate de identidad Tvheadend PASS; gate end-to-end Kodi sigue pendiente.** Siguiente: preflight sólo lectura sobre binario Kodi, procesos, perfil activo y pvr.hts; preparar otro perfil, otro puerto JSON-RPC, sin reutilizar `/runtime/kodi_home/.kodi`, ni reemplazar ni detener la instancia G3-AB.

```text
G3AM_TVH_RENAME_IDENTITY=PASS
G3AM_TVH_CHANNEL_COUNT=2
G3AM_ALPHA_NAME=G3AM Alpha Renamed
G3AM_BETA_NAME=G3AM Beta
G3AM_PERSISTENT_HTSP_CHANNELUPDATE=PASS
G3AM_KODI_G3AM_PROFILE=NOT_STARTED
```

## G3-AM — Kodi local disponible, aislamiento preparado (22/11/2026)

Preflight operador:

```text
/usr/bin/kodi
/usr/bin/kodi-standalone
kodi 2:21.3+dfsg-1ubuntu1
kodi-bin 2:21.3+dfsg-1ubuntu1
kodi-pvr-hts 21.2.6+ds-1.1
KODI_PROCESSES=NONE
/usr/lib/x86_64-linux-gnu/kodi/addons/pvr.hts/pvr.hts.so.21.2.6
/usr/share/kodi/addons/pvr.hts
DISPLAY=:0
WAYLAND_DISPLAY=wayland-0
XDG_SESSION_TYPE=wayland
```

Kodi sistema disponible y complemento instalado globalmente; no se requiere instalar ni copiar los archivos de addon. Aún no existe perfil G3-AM: crear exclusivamente `runtime/g3am/kodi_home` con modo 0700 y guardas de marca sintética, dueño, no symlink, sin tocar perfil G3-AB `runtime/kodi_home/.kodi`. Inicio propuesto con `env HOME=$PWD/runtime/g3am/kodi_home kodi --windowing=wayland` desde shell con sesión gráfica; el perfil Linux reside en `$HOME/.kodi` (documentación Kodi wiki). No usar --portable para Linux. Solo un proceso Kodi a la vez (ninguno previo activo), UI PVR HTSP endpoint host 127.0.0.1 port 29992, credenciales vacías solo en este TVH G3-AM --noacl. Activar complemento global `pvr.hts` mediante UI. Verificar explícitamente `runtime/g3am/kodi_home/.kodi` creado y que G3-AB sigue intacto, luego snapshot PVR.GetChannels; Kodi HTTP JSON-RPC no habilitado inicialmente (puertos 8080/8081 no escuchan). La playlist está en estado `rename` y Alpha `G3AM Alpha Renamed`: para prueba de sincronización cambiar a baseline y luego rename con Kodi arrancado, preservando CUID, channel UUID Tvheadend y Kodi channelid.

```text
G3AM_KODI_BINARY=AVAILABLE_21.3
G3AM_PVR_HTS_ADDON=AVAILABLE_21.2.6
G3AM_KODI_RUNNING=NO_AT_PREFLIGHT
G3AM_KODI_PROFILE_CREATED=NOT_YET_CONFIRMED
G3AM_KODI_PVR_SYNC=NOT_TESTED
```
