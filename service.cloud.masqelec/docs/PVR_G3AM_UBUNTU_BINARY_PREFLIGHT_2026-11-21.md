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
