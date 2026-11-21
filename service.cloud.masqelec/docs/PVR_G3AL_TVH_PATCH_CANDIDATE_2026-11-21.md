# G3-AL — Candidato de parche Tvheadend: notificación HTSP selectiva tras rename IPTV

**Fecha:** 2026-11-21. **Objetivo:** demostrar que la modificación de un nombre efectivo recibida de M3U produce `channelUpdate` en el **mismo socket HTSP** y que Kodi mantiene sus IDs, sin reiniciar PVR, hacer rescan del bouquet ni escribir en SQLite.

## Estado real

```text
G3AL_CANDIDATE_PATCH_COMMITTED=YES
G3AL_PATCH_EXACT_SOURCE_HUNKS_VERIFIED=5
G3AL_GIT_APPLY_CHECK_ON_UBUNTU=PENDING
G3AL_COMPILATION=PENDING
G3AL_RUNTIME_TEST=PENDING
G3AL_PRODUCTION_AUTHORIZED=NO
G3AL_PRODUCTION_DEPLOYED=NO
```

Archivo: `lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch`. **NO está aplicado al contenedor Tvheadend** ni se ha construido nueva imagen. Los cinco hunks se han contrastado uno a uno contra `tvheadend/tvheadend@8837853a6`; falta el `git apply --check` de una copia real en Ubuntu y la compilación.

## Fundamento de revisión fuente exacta

- `src/input/mpegts/iptv/iptv_auto.c`: en un multiplexor existente con URL coincidente, cambia `im->mm_iptv_svcname`, pero solo notifica al idnode del mux, no a canales HTSP.
- `src/input/mpegts/iptv/iptv_service.c`: `iptv_service_channel_name()` devuelve `im->mm_iptv_svcname` dinámicamente si no vacío; la consulta de nombre efectivo del canal puede cambiar sin tocar nombre persistente.
- `src/channels.c`: `channel_get_name()` prefiere nombre fijo `ch_name`, o nombre de servicio enlazado; `autoname=True` para los dos canales de G3-AB.
- `src/input/mpegts/mpegts_mux.c`: `mm_services` / `s_channels` permiten encontrar **solo canales enlazados**.
- `src/htsp_server.c`: `htsp_channel_update(ch)` envía `channelUpdate` a clientes HTSP asíncronos autorizados; no modifica mapping.
- `src/download.c`: descarga HTTP ejecuta callback M3U bajo `global_lock`. **Candidato restringe notificación a `http://` y `https://`**, no a rutas file/pipe todavía no auditadas.

## Comportamiento candidato

Cuando cambie `mm_iptv_svcname` en multiplexor existente:

1. Antes de cambiarlo, tomar snapshot solo de los canales asociados a sus servicios que tengan `ch_autoname` activado y sin `ch_name` fijo. Deduplicar por puntero `channel_t*`.
2. Guardar nombre efectivo previo usando `channel_get_name()`. Si falla reserva de memoria, continuar recarga normal **pero no enviar notificaciones parciales**.
3. Cambiar valor de `mm_iptv_svcname` usando lógica existente, sin tocar `ch_name`, enlaces, bouquets, base de datos ni ID.
4. Para cada canal en snapshot, comparar nombre efectivo actual contra nombre previo y llamar a `htsp_channel_update(ch)` **solo si cambió**.
5. Liberar siempre el snapshot. Repetir M3U idéntica no debe producir notificaciones; cambios ajenos al nombre conservan comportamiento previo.

**No es seguro generalizar este candidato a todos los sistemas sin laboratorio**: no se ha demostrado compilación, comportamiento cuando varios servicios comparten canal, que los tags/LCN/hot order tengan el mismo defecto, ni compatibilidad de CoreELEC. La notificación del nombre no resuelve por sí sola eliminación/orden de canales en Kodi.

## Preflight EXCLUSIVAMENTE offline en Ubuntu

Desde `/home/ubuntu/GitHub/service.cloud.masqelec`:

```bash
git pull --ff-only origin develop

# No utilizar el árbol del addon para el checkout upstream.
cd /home/ubuntu

if [ ! -d tvheadend-g3al-upstream/.git ]; then
  git clone --filter=blob:none https://github.com/tvheadend/tvheadend.git tvheadend-g3al-upstream
fi
cd tvheadend-g3al-upstream
git fetch --filter=blob:none origin
git checkout --detach 8837853a6

git status --short
git rev-parse --short=9 HEAD

git apply --check \
  /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch

echo "G3AL_PATCH_APPLY_CHECK=PASS"
```

**Precaución:** `git clone` y `git fetch` requieren Internet; si falla acceso o la revisión no coincide, `G3AL_BLOCKED`. `git apply --check` **no modifica archivos**. No ejecutar todavía `git apply` sobre el checkout, ni desplegar imagen. El subdirectorio `_lab_upstream` es un árbol separado, no debe añadirse al repositorio; al estar dentro del repo del addon puede aparecer como carpeta sin seguimiento: mantener fuera de commits.

**Límites del gate**: el preflight es solo comprobación estructural; la compilación y validación HTSP requieren otro gate y decisión explícita de sustituir el **contenedor de laboratorio** con rollback, nunca `latest` en producción.

## Plan del gate runtime posterior (no ejecutado)

- Preparar copia de configuración/estado G3-AB + imagen derivada `tvheadend:g3al-lab`, no reusar `latest`; conservar Docker config persistente y poder revertir.
- Mantener sesión HTSP abierta y capturar `channelUpdate` mediante G3-AH, con SYN/puertos del cliente invariantes durante `prepare.py rename` → importación M3U.
- Comprobar nombre Kodi renombrado sin reproducción ni reconexión y `channelid=3`/Beta=2; conservar UUID, servicios, autoname, protección de grupos, sin pérdidas.
- Probar rename inverso, M3U sin cambio, múltiple servicio, iconos/tags separados y replay de corte sin propagación de IDs.
- Abortar ante falla de invariantes y conservar PCAP privado.

## Riesgos a evaluar

- Es una modificación de Tvheadend, no del addon. Necesitaría distribución, mantenimiento y actualización de un binario diferente para usuarios de masQelec.
- No inferir que CUID M3U equivale a identificador Tvheadend/Kodi.
- La actualización de nombre no valida aún la gestión integral del mantenimiento PVR (eliminación, cambio de URL, orden y grupos). La transición completa no está autorizada.

## G3-AL: `git apply --check` confirmado por operador; siguiente compilación aislada (21/11/2026)

El operador ejecutó checkout fuente exacto separado `/home/ubuntu/tvheadend-g3al-upstream`, obtuvo:
```text
HEAD está ahora en 8837853a debian: enable IPv6 under systemd as well
8837853a6
G3AL_PATCH_APPLY_CHECK=PASS
```
No informó modificaciones al checkout upstream ni al contenedor de laboratorio. El echo PASS siguió a `git apply --check`; la orden anterior no imprimió error. Gates: `G3AL_UPSTREAM_CHECKOUT=8837853a6`, `G3AL_GIT_APPLY_CHECK_UBUNTU=PASS`, `G3AL_PATCH_APPLIED_TO_CHECKOUT=NO_BEFORE_NEXT_GATE`, `G3AL_COMPILE=PENDING`.

En la fuente original `Dockerfile` del commit `8837853a6` existen builder y runner Alpine. El builder ejecuta `./configure` con `--disable-ffmpeg_static --disable-libav --disable-doc` y `make install` con dependencias de compilación; el runner utiliza biblioteca/ABI de Alpine, **no debe sustituirse directamente un binario sobre el contenedor LinuxServer del lab sin confirmar compatibilidad de ABI y configuración**. Si se prueba build, preferir imagen Docker separada con tag propio, sin pasar `--build` sobre servicio TVH activo y sin reusar sus volúmenes.

Siguiente gate limitado a compilación de **copia de código**:
```bash
cd /home/ubuntu/tvheadend-g3al-upstream
test "$(git rev-parse HEAD)" = "$(git rev-parse 8837853a6)" || exit 2
test -z "$(git status --porcelain)" || { echo "BLOCKED_DIRTY_UPSTREAM"; exit 2; }
git apply /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch
git diff --check
./configure --disable-ffmpeg_static --disable-libav --disable-doc
make -j2
```
No ejecutar `make install` en host, no lanzar servidor ni reiniciar contenedores. Si `./configure` falla por dependencias del host, **no instalar paquetes automáticamente**: capturar el mensaje concreto, preparar builder Docker aislado si procede. Los comandos `git apply` modifican solo `/home/ubuntu/tvheadend-g3al-upstream`, un checkout aparte. `make -j2` limita concurrencia y puede ocupar recursos del host; no confundir éxito de configure con binario funcional.

**Observación de riesgo**: validar la compilación incluye comprobar declaraciones de tipos de `mpegts_service_t`, `htsp_channel_update`, `idnode_list_mapping_t` y el acceso a `in->in_url`. Si compila, realizar diff de símbolos y posteriormente montar ensayo de contenedor alternativo respaldado; todavía no autorizado despliegue producción.

`G3AL_COMPILE=NOT_YET_EXECUTED`
`G3AL_CONTAINER_SWAPPED=NO`
`G3AL_RELEASE_AUTHORIZED=NO`

## G3-AL host configure #1: falló por libdvbcsa, NO por compilación del parche (21/11/2026)

El operador ejecutó en checkout upstream aislado `/home/ubuntu/tvheadend-g3al-upstream`:
```text
G3AL_PATCH_APPLIED=PASS
checking for python binary ... WARN: no python binary found
checking for py module gzip ... fail
libpcre2-8 ... fail
libpcre ... fail
liburiparser ... fail
avahi-client ... fail
dvbcsa/dvbcsa.h ... fail
ERROR: Failed to find dvbcsa library
./configure output is old, please re-run
Makefile:770: /support/.mk: No existe ...
make: *** No hay ninguna regla para construir el objetivo '/support/.mk'.
```

**Resultado**: `git apply` y `git diff --check` PASS. La compilación C del parche NO fue alcanzada porque `configure` abortó; el error Makefile es secundario por falta de `.config.mk` generado. No declarar error de tipo o falla de parche en C, ni gate de compilación PASS.

Se revisó `configure` exacto `tvheadend/tvheadend@8837853a6`:
- defaults `cwc:yes,cccam:yes,capmt:yes,constcw:yes,tvhcsa:auto`, `iptv:yes`, `dvbscan:yes`, `vue_build:auto`.
- líneas ~812–824: si cardclient está habilitado, `tvhcsa` se activa y exige cabecera/librería `dvbcsa`; `--disable-cwc --disable-cccam --disable-capmt --disable-constcw --disable-tvhcsa` evita esa ruta únicamente para compilar, sin representar build con paridad de funcionalidades.
- `--python=python3` corrige el `python` ausente si python3 está instalado, sin symlinks de sistema.
- `--disable-dvbscan` evita descarga innecesaria durante preflight, `--disable-vue_build` evita build frontend. `--disable-ffmpeg_static --disable-libav --disable-doc` ya indicados.
- Faltas `libpcre2`, `liburiparser`, Avahi eran comprobaciones opcionales en esta configuración, pero pueden aparecer otros fallos más adelante.
- Nuevo gate propuesto: ejecutar solo `./configure ...` con flags reducidos, usando `&& make -j2` **únicamente si configure termina con éxito**. No instalar paquetes de host automáticamente ni modificar contenedor TVH.
- Aunque compile con funciones reducidas, **NO autoriza usar este binario en el contenedor** (no incluye mismas prestaciones/ABI que imagen LinuxServer).

`G3AL_PATCH_APPLIED_TO_ISOLATED_UPSTREAM=PASS`
`G3AL_HOST_CONFIGURE_1=FAIL_LIBDVBCSA_MISSING`
`G3AL_C_SOURCE_COMPILATION=NOT_REACHED`
`G3AL_TVH_LAB_CONTAINER_CHANGED=NO`

## G3-AL: compilación con opciones reducidas alcanza enlace final; exit code pendiente (2026-11-21)

Tras configure con `--python=python3 --disable-ffmpeg_static --disable-libav --disable-doc --disable-cwc --disable-cccam --disable-capmt --disable-constcw --disable-tvhcsa --disable-dvbscan --disable-vue_build`, el operador comunicó las últimas líneas:

```text
CC              src/input/mpegts/tvhdhomerun/tvhdhomerun.o
CC              src/input/mpegts/tvhdhomerun/tvhdhomerun_frontend.o
CC              src/docs.o
CC              timestamp.o
CC              tvheadend
```

Indican llegada a etapa de enlace final, sin error en el fragmento recibido. **No se ha recibido código de salida, ni verificación del binario, ni informe completo**. Estado `G3AL_BUILD_LINK_REACHED=YES`, `G3AL_COMPILE_PASS=PENDING_EXIT_CHECK`. El build reducido no asegura paridad funcional ni ABI con imagen LinuxServer `latest`, por lo que no usar el binario para sustituir servicio. Siguiente comando en checkout experimental: `make -j2 && test -x build.linux/tvheadend && echo G3AL_COMPILE=PASS` con comprobación de ruta del ejecutable antes de asumir el destino concreto; si ruta distinta, consultar `find build.* -type f -name tvheadend`. No arranque ni deploy.
