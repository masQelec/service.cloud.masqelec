# RUNBOOK G3-AB — Laboratorio persistente Ubuntu (21/11/2026)

**Propósito:** conservar y reutilizar el laboratorio real del operador en Ubuntu para las pruebas PVR HTSP y Tvheadend personalizadas. **No recrear desde cero**, no asumir que sigue ejecutándose después de cerrar el chat, no confundir el laboratorio con producción CoreELEC.

## 1. Inventario conocido y verificado

Directorio de trabajo:
```text
/home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab
```

Archivo Compose existente: `compose.yaml`, proyecto `masqelec-pvr-g3ab`:
- `tvh`: `lscr.io/linuxserver/tvheadend:latest`; HTTP `127.0.0.1:19991 -> 9981`, HTSP `127.0.0.1:19992 -> 9982`; `PUID/PGID` por defecto 1000; TZ Europe/Madrid; `restart: "no"`.
- `streams`: `nginx:alpine`, sirve MPEG-TS sintéticos en la red Docker `pvr_g3ab`, no publica puerto HTTP del contenedor al host.
- Volúmenes: `./runtime/tvh_config:/config` **escritura**, `./runtime/recordings:/recordings` **escritura**, `./runtime/playlist:/lab_playlist:ro`, `./runtime/streams:/usr/share/nginx/html:ro`.
- Kodi Linux fuera de esos contenedores: JSON-RPC HTTP `127.0.0.1:8080/jsonrpc`; la instancia del laboratorio ha utilizado `runtime/kodi_home/.kodi`, y `pvr.hts` conecta al HTSP publicado en 19992. La instancia Kodi no está definida en el Compose y debe inspeccionarse aparte; no lanzar una segunda Kodi sobre el mismo perfil.
- El runtime `runtime/` **es estado local persistente y sensible**, no fuente Git versionada. Conservarlo, no subir directorios de configuración ni PCAP.

Contenedores que el operador observó en marcha después de ocho horas:
```text
masqelec-pvr-g3ab-tvh-1       lscr.io/linuxserver/tvheadend:latest  Up 8 hours
masqelec-pvr-g3ab-streams-1   nginx:alpine                           Up 8 hours
```
**Importante:** “Up 8 hours” es una observación histórica del 21/11/2026, no una comprobación de disponibilidad en el chat siguiente. Revalidar con `docker compose ps` sin destruir el entorno.

Identidad/versiones observadas:
```text
TVH: 4.3-2897~g8837853a6
LinuxServer: 8837853a-ls288, build 2026-10-17T17:55:41+00:00
TVH image sha256:7f5d04ed7ea7f58cd50c2cf11a79d0823fa0a4aa4f6c64478360b9e3a8027c28
TVH API:20
Kodi JSONRPC: http://127.0.0.1:8080/jsonrpc
```

## 2. Generador de pruebas y datos inmutables

`prepare.py` solo escribe bajo `lab/pvr_g3ab/runtime` y exige marca `runtime/.g3ab-synthetic-only` con contenido `masqelec-g3ab-synthetic-v1\n`. Usa escritura atómica de la M3U. Genera CUID estable `g3ab-001` Alpha y `g3ab-002` Beta. Requiere `ffmpeg` solo para generar MPEG-TS iniciales si aún no existen.

Escenarios explícitos: `baseline`, `rename`, `url`, `group`, `reorder`, `homonym`, `restored`. Cada escenario se construye desde dos entradas base, no de un estado anterior. **No ejecutar `prepare.py` hasta tomar snapshot y planificar el gate**: modifica la playlist y puede desencadenar actualización de Tvheadend cada minuto. Último estado de playlist comunicado: `rename`, Alpha `G3AB Alpha Renamed`; verificar antes de modificar.

Archivos de evidencia local:
- `runtime/htsp_capture/g3af_rename.pcap`
- `runtime/htsp_capture/g3af_playback.pcap`
- `runtime/kodi_home/.kodi/temp/kodi.log`
- Snapshot de canales TVH desde `GET /api/channel/grid`
- Snapshot de propiedades canal desde `GET /api/idnode/load?uuid=...`, **leer `entries[].params` y no `props`**.
- Snapshot Kodi desde JSON-RPC `PVR.GetChannels`, grupo `alltv`.
No compartir PCAP bruto, tokens o configuración privada.

Identidades registradas tras el ensayo de rename:
```text
Alpha UUID: dba29285ca808eb6486d364f994b05db
Alpha service: e98c6fdf8c5a5e16e3ea122319f9977b
Alpha name: G3AB Alpha Renamed
Alpha autoname=True, enabled=True
Kodi Alpha channelid=3

Beta UUID: 3bf90ae8eb828a6e4961902724a1f380
Beta service: afe6f317e9b95eb03f6d91691e80f537
Beta name: G3AB Beta
Beta autoname=True, enabled=True
Kodi Beta channelid=2
```
Son valores **históricos de este laboratorio**, no requisitos que deban restablecerse artificialmente. Si difieren en el siguiente chat, investigar antes de borrar o recrear.

## 3. Checkout Tvheadend personalizado separado

```text
/home/ubuntu/tvheadend-g3al-upstream
  Git detached HEAD 8837853a6
  parche G3-AL aplicado al archivo src/input/mpegts/iptv/iptv_auto.c
  ejecutable generado ./build.linux/tvheadend
```

Parche versionado en el repo del addon:
`lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch`.

Gates certificados por salida del operador: `git apply --check=PASS`, `git apply=PASS`, `git diff --check=PASS`, `make -j2=PASS`; no existe prueba runtime del ejecutable. `configure` Ubuntu host se hizo con funciones reducidas (sin acceso condicional, FFmpeg integrado, DVB scan, documentación/Vue). **No instalar ese binario sobre LinuxServer ni CoreELEC, no ejecutar make install**; no asumir paridad de ABI o prestaciones.

El usuario tiene preparado **otro entorno de build de CoreELEC**; su ruta, plataforma y toolchain exactos no se han comunicado. Revisarlos cuando se alcance la fase de compilación de binario final. **No confundir ese entorno con este checkout Linux de Tvheadend**.

## 4. Comprobaciones seguras al entrar al siguiente chat

Comandos de **solo lectura**:
```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab
pwd
docker compose ps
docker compose images
test -f runtime/.g3ab-synthetic-only && echo G3AB_MARKER=PRESENT
test -f runtime/playlist/playlist.m3u && echo G3AB_PLAYLIST=PRESENT
test -d runtime/tvh_config && echo G3AB_TVH_CONFIG=PRESENT
test -d runtime/kodi_home/.kodi && echo G3AB_KODI_PROFILE=PRESENT
test -f runtime/htsp_capture/g3af_rename.pcap && echo G3AB_RENAME_PCAP=PRESENT
test -f runtime/htsp_capture/g3af_playback.pcap && echo G3AB_PLAYBACK_PCAP=PRESENT

cd /home/ubuntu/tvheadend-g3al-upstream
git rev-parse --short=9 HEAD
git status --short
file ./build.linux/tvheadend
ldd ./build.linux/tvheadend
./build.linux/tvheadend --version
```
`git status --short` en upstream debe mostrar archivos modificados: **es normal porque el parche está aplicado**; no ejecutar `git reset --hard` ni `git clean -fdx` para “limpiarlo”. No ejecutar `docker compose down -v` ni `prepare.py baseline` solo para iniciar un chat.

## 5. Reglas de aislamiento y reversión para G3-AM

La siguiente fase **no** consiste en reemplazar el servicio activo, sino levantar **otro Tvheadend de ensayo** con puertos exclusivos (propuestos 29991/29992), configuración propia y playlist/streams propios. No montar `runtime/tvh_config` en escritura en más de un proceso. No sobrescribir ni modificar Kodi `runtime/kodi_home/.kodi`; usar cliente o perfil aparte para pruebas controladas, o diseñar corte verificable con rollback si después se justifica.

Antes de iniciar ese servicio:
1. Verificar ABI del ejecutable, librerías y opciones de compilación.
2. Confirmar red Docker y acceso al host `streams` desde la nueva instancia; no suponer que `http://streams/ch1.ts` resolverá si está fuera de red `pvr_g3ab`.
3. Preparar configuración independiente derivada de snapshot o inicializada con identidades deliberadas; nunca reusar config original RW.
4. Registrar SHA/digest de imagen y backup de config; preparar rollback sin tocar original.
5. Ejecutar test rename con socket HTSP estable y PCAP analizado por `tools/pvr_g3ah_htsp_pcap.py`: evento `channelUpdate` válido sobre conexión ya abierta. Verificar en Kodi con perfil de ensayo, sin playback ni reconexión.
6. Validar que ID/servicios/autoname persistentes no cambian y que recarga M3U sin cambios no genera actualización innecesaria. No tocar grupos protegidos.
7. No concluir compatibilidad con CoreELEC hasta compilar después con el build del usuario.

**Este runbook registra el estado conocido.** Una carpeta presente o un contenedor con nombre conocido no implica que el programa siga abierto. No enviar comandos destructivos sin conocer el estado actual.

## 6. Trabajo siguiente al PVR

EPG-01: géneros de la guía de Kodi siempre “Otros”/“Desconocidos”. Sin diagnóstico. Tras gate PVR, inspeccionar un `<programme>` y `<category>` reales del XMLTV, luego importación/mapeo Tvheadend y HTSP/Kodi; no asumir el XML defectuoso.

## 7. Documentos vinculados

- `docs/HANDOFF_TVH_CUSTOM_CORELEC_EPG_2026-11-21.md`: estado general, metodología y prioridades.
- `docs/HANDOFF_PVR_G3W_TO_G3AC_2026-11-21.md`: cronología completa.
- `docs/PVR_G3AH_HTSP_PCAP_DECODER_2026-11-21.md`: método de lectura HTSP.
- `docs/PVR_G3AK_TVH_CHANNEL_NOTIFY_DESIGN_2026-11-21.md`: diseño de notificaciones.
- `docs/PVR_G3AL_TVH_PATCH_CANDIDATE_2026-11-21.md`: parche compilado, aún sin gate runtime.

```text
G3AB_LAB_EXISTING_ON_OPERATOR_UBUNTU=YES_HISTORICAL
G3AB_CURRENT_RUNNING_STATUS=RECHECK_NEXT_CHAT
G3AB_ORIGINAL_CONFIG_PRESERVE=YES
G3AB_ORIGINAL_KODI_PROFILE_PRESERVE=YES
G3AL_PATCHED_HOST_BINARY_BUILD=PASS
G3AL_PATCHED_BINARY_RUNTIME=NOT_TESTED
G3AM_PARALLEL_TVH_RUNTIME=NOT_STARTED
G3AM_CORELEC_BUILD=NOT_STARTED
```
