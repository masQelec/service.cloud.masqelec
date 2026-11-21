# HANDOFF — Tvheadend personalizado, PVR nativo y siguiente incidencia EPG (2026-11-21)

> **Estado de cierre de chat, 21/11/2026.** Rama de trabajo `develop`. Este documento es el punto de entrada del próximo chat. Los documentos G3-W→G3-AL contienen cronología y pruebas exhaustivas.

## 1. Objetivo técnico y decisiones del propietario

El usuario mantiene el addon `service.cloud.masqelec` para CoreELEC/masQelec y el mantenimiento PVR de Kodi/Tvheadend. Quiere un mantenimiento fiable de M3U (CUID estable), nombres, URLs, orden, altas/bajas y grupos, sin manipular directamente SQLite Kodi, sin recrear canales injustificadamente, sin borrar bouquets/grupos protegidos y sin conmutaciones de `pvr.hts` como solución rutinaria. Kodi puede actualizar el addon automáticamente mediante el repositorio del usuario; publicación de paquetes por el usuario.

**NOVEDAD explícita**: el usuario **ya tiene preparado un entorno de build CoreELEC** para compilar un binario personalizado si resulta necesario. Prefiere adaptar la aplicación/código a sus necesidades antes que aceptar workarounds frágiles. No se ha recibido aún la ruta/arquitectura/toolchain exacta de ese entorno. **No asumir que el ejecutable host Ubuntu es ejecutable en CoreELEC, ni reutilizar flags reducidos para la versión final**.

**SIGUIENTE INCIDENCIA** expresamente solicitada después del problema PVR: la **guía EPG muestra los géneros siempre como «Otros» o «Desconocidos»**. El usuario sospecha de lectura XML u otra causa. **Aún no se ha auditado esta incidencia y no se ha demostrado que el XML sea defectuoso.** Registrar como prioridad futura EPG-01; investigar después de cerrar la notificación PVR. No modificar el parser XML ni clasificación de géneros a ciegas.

## 2. Evidencia demostrada: G3-AB → G3-AJ

Laboratorio aislado: `service.cloud.masqelec/lab/pvr_g3ab`, Tvheadend LinuxServer `lscr.io/linuxserver/tvheadend:latest` sobre Docker HTTP `127.0.0.1:19991`, HTSP `127.0.0.1:19992`, servidor de streams `nginx:alpine`, Kodi Linux JSONRPC `127.0.0.1:8080`. Compose en `lab/pvr_g3ab/compose.yaml`. El laboratorio tiene configuración persistente `runtime/tvh_config`; **no permitir dos procesos con ese mismo volumen en escritura**.

Identificación de Tvheadend del contenedor:
```text
SW_VERSION=4.3-2897~g8837853a6
API_VERSION=20
LinuxServer build_version=8837853a-ls288
Build-date=2026-10-17T17:55:41+00:00
IMAGE_SHA256=7f5d04ed7ea7f58cd50c2cf11a79d0823fa0a4aa4f6c64478360b9e3a8027c28
```

M3U sintética con CUIDs `g3ab-001` / `g3ab-002`, generada por `prepare.py`; escenarios `baseline`, `rename`, `url`, `group`, `reorder`, `homonym`, `restored`. **No intercambiar CUID con UUID TVH o channelid de Kodi**.

Snapshot validado con APIs:
```text
TVH Alpha UUID = dba29285ca808eb6486d364f994b05db
TVH Alpha service = e98c6fdf8c5a5e16e3ea122319f9977b
TVH Alpha name = G3AB Alpha Renamed; autoname=True; enabled=True
TVH Beta UUID = 3bf90ae8eb828a6e4961902724a1f380
TVH Beta service = afe6f317e9b95eb03f6d91691e80f537
TVH Beta name = G3AB Beta; autoname=True; enabled=True
Kodi Alpha channelid = 3
Kodi Beta channelid = 2
```

El renombrado del canal en la M3U cambió el nombre efectivo de Tvheadend manteniendo UUID/servicios, pero Kodi permaneció con nombre anterior durante 40 muestras (~195 segundos). PCAP capturado alrededor del cambio: **32 paquetes TCP según lector G3-AH, 0 con payload, 0 SYN, todos midstream** (conteo anterior `tcpdump` 28: discrepancia numérica no explicada). No mostró evento HTSP hacia Kodi durante la ventana.

Durante la reproducción posterior, sí hubo dos conexiones nuevas HTSP desde Kodi (puertos cliente 49262 y 40098, antes 46266). Captura playback: **1501 paquetes, 1024 con payload**, 4 SYN, 455 midstream. Decodificador HTSP G3-AH confirmó sesiones servidor→Kodi:
```text
port 49262: 668 frames HTSP válidos; channelAdd=2, channelName presente=2,
            initialSyncCompleted=1, tagAdd=2, tagUpdate=2,
            invalid=0, desync=False.
port 40098: 434 frames HTSP válidos; channelAdd=2, channelName presente=2,
            initialSyncCompleted=1, tagAdd=2, tagUpdate=2,
            invalid=0, desync=False.
```
Kodi acabó mostrando `G3AB Alpha Renamed` y los mismos channelid 3/2. **Conclusión demostrada**: la nueva sincronización HTSP recibió los nombres nuevos. **No atribuir el refresco exclusivamente a la reproducción**: coincidió con conexiones nuevas. No se demostró recepción interna de pvr.hts ni emisión de `channelUpdate` en el renombrado anterior.

Lector offline: `tools/pvr_g3ah_htsp_pcap.py`; **12/12 tests Ubuntu PASS**, lectura y validación sin mostrar secretos. No subir PCAP crudos a GitHub.

## 3. Causa técnica probable, verificada contra upstream exacto

La fuente Tvheadend en `tvheadend/tvheadend@8837853a6` muestra:
- `src/input/mpegts/iptv/iptv_auto.c`: al cambiar el nombre de una entrada M3U sobre mux existente (misma URL de comparación), modifica `im->mm_iptv_svcname` y ejecuta `idnode_notify_changed(&im->mm_id)`; no envía directamente `htsp_channel_update`.
- `src/input/mpegts/iptv/iptv_service.c`: `iptv_service_channel_name` retorna dinámicamente `mm_iptv_svcname`, o el nombre del servicio como fallback.
- `src/channels.c`: `channel_get_name` usa nombre manual no vacío o el nombre del servicio; `channel_class_changed` ejecuta `htsp_channel_update(ch)`.
- `src/htsp_server.c`: `htsp_channel_update` emite `channelUpdate` a sesiones HTSP asíncronas autorizadas.
- `src/idnode.c`: `idnode_notify_changed` notifica idnode pero no garantiza ejecutar callback de cambio de canal. Escribir valores iguales por API tampoco garantiza trigger HTSP.
- `src/input/mpegts/mpegts_mux.c`: navegación desde `mm_services` a `s_channels` permite dirigirse a canales afectados.
- `src/download.c`: procesamiento de **playlist HTTP(S)** ocurre bajo `global_lock`.
- `src/bouquet.c`: un remap/rescan puede desmapear o incluso borrar canales. **Nunca usar bouquet como gatillo artificial**.

**Hipótesis de alta confianza, aún no validada por parche runtime**: nombre nuevo se ve por API de TVH porque es heredado, pero falta aviso HTSP de actualización de canal en la conexión existente. Un rename con URL cambiada puede recrear mux/servicio/canal; no confundir esta observación con el escenario de nombre-only. Manipulación manual de bouquet en pruebas anteriores contaminó IDs de esa fase; no atribuir al overwrite atómico.

## 4. G3-AL — Parche EXPERIMENTAL YA COMPILADO, NO DESPLEGADO

En `develop`:
```text
lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch
docs/PVR_G3AK_TVH_CHANNEL_NOTIFY_DESIGN_2026-11-21.md
docs/PVR_G3AL_TVH_PATCH_CANDIDATE_2026-11-21.md
```

El parche C modifica solamente `src/input/mpegts/iptv/iptv_auto.c` del Tvheadend exacto. Para renombrado real y solo en origen playlist HTTP(S), toma snapshots de nombres efectivos anteriores para canales vinculados al mux con `ch_autoname` y sin nombre fijo, deduplica por puntero, actualiza nombre mux con la lógica previa, compara nombres antes/después y llama a `htsp_channel_update(ch)` únicamente si el nombre efectivo cambió. Evita fijar `ch_name`, tocar servicios, bouquet, SQLite, etc. Si falla memoria, la recarga original continúa sin nuevos avisos. Rutas file/pipe deliberadamente no incluidas hasta auditar locks.

Evidencia de operador desde Ubuntu:
```text
checkout upstream aislado = /home/ubuntu/tvheadend-g3al-upstream
git HEAD = 8837853a6
git apply --check = PASS
git apply = PASS
git diff --check = PASS
configuración original host (con dvbcsa) = FAIL en configure por dependencia ausente
configuración reducida (sin acceso condicional, FFmpeg, DVB scan, docs/Vue) = apta para compilar
G3AL_MAKE=PASS
BINARY=./build.linux/tvheadend
```
**Importante**: el binario Ubuntu fue compilado con funciones deshabilitadas, no es la versión que se instalaría en CoreELEC, ni existe evidencia de que funcione como servidor HTTP/HTSP con su configuración. No usarlo para reemplazar LinuxServer ni copiarlo a CoreELEC. No correr `make install` en el host.

```text
G3AL_PATCH_APPLY=PASS
G3AL_HOST_MAKE=PASS
G3AL_BINARY_RUNTIME=NOT_TESTED
G3AL_HTSP_CHANNELUPDATE_HOT_RENAME=NOT_TESTED
G3AL_KODI_ID_PRESERVATION_WITH_PATCH=NOT_TESTED
G3AL_CORELEC_BUILD=NOT_STARTED
G3AL_PRODUCTION_DEPLOY=NO
```

## 5. Decisión nueva: usar entorno CoreELEC existente para futuro binario final

Usuario indica que **tiene preparado el entorno de compilación CoreELEC**. En el siguiente chat, cuando corresponda pasar del laboratorio al binario final:
1. Identificar arquitectura/plataforma/commit del fork, versión TVH empaquetada, ruta del package y flags/toolchain del entorno **sin inventar rutas**; revisar build ya existente y evitar instalar toolchains duplicados.
2. Hacer primero ensayo G3-AM de runtime aislado, en una instancia independiente con config propia; un build host Ubuntu no sustituye ese gate. Considerar si conviene compilar TVH de laboratorio con Docker builder de la fuente original / imagen aislada compatible; no compartir ni copiar el volumen `runtime/tvh_config` en escritura.
3. Si el parche supera HTSP/canales en laboratorio y se decide incorporarlo, **portar/compilar el cambio en el build CoreELEC disponible del usuario** respetando flags y configuración, antes de evaluar distribución por addon/fork. No editar master CoreELEC ni desplegar sin autorización explícita.
4. Evaluar mantenimiento de un fork de Tvheadend (actualizaciones upstream, seguridad, reproducibilidad y soporte de usuarios), no asumir que compilación exitosa resuelve todo el mantenimiento PVR.

**Siguiente gate inmediato G3-AM**: desde `/home/ubuntu/tvheadend-g3al-upstream`:
```bash
file ./build.linux/tvheadend
ldd ./build.linux/tvheadend
./build.linux/tvheadend --version
```
Luego planificar segunda instancia de prueba sin reutilizar config activa ni puertos 19991/19992. Comprobar salida `channelUpdate` en la misma sesión HTSP al renombrar la M3U y actualización Kodi sin playback/reconexión; verificar UUID, service IDs, autoname y channel IDs. No lanzar la segunda instancia antes de preparar aislamiento y rollback.

## 6. FUTURO EPG-01 — Géneros «Otros» / «Desconocidos»

**Reporte del usuario**: en la guía de TV, los géneros aparecen siempre como `Otros` o `Desconocidos`. Desconoce si el fallo es la interpretación del XML o una transformación posterior. No hay captura del XML de ejemplo ni prueba que determine origen. **No dar como hecho que el XML esté mal.**

Al completar PVR, abrir una auditoría específica y comparativa, inicialmente solo lectura:
1. Identificar qué guía EPG se consume exactamente: fuente XMLTV original, proceso de carga/EPG grabber Tvheadend, metadatos que entrega TVH por API/HTSP, presentación Kodi/pvr.hts y traducción/localización.
2. Revisar unos ejemplos concretos de `<programme>` y `<category>` (categoría de XMLTV textual, idioma/locale); comparar canal/evento idéntico en cada capa. El origen exacto de los tags/códigos debe verificarse.
3. Verificar si Tvheadend interpreta categorías como texto libre y cómo convierte a `genre` numérico o etiqueta, y cómo Kodi/pvr.hts traduce esos valores. Los géneros pueden depender de mapeos DVB/content descriptors, configuración, traducciones o falta real de categoría; **todas son hipótesis**.
4. Diseñar tabla de equivalencias reproducible y tests de muestra — si procede — sin inventar categorías, sin perder descriptores y sin alterar EPG en producción antes de ensayo aislado.
5. Separar parche Tvheadend de la corrección EPG, pruebas y commits; documentar compatibilidad de la compilación final CoreELEC.

**No realizado**: análisis del XML, API EPG, Kodi UI/genre parsing, código de genre mapping, pruebas, modificación de EPG.

```text
EPG01_REPORTED_BY_USER=YES
EPG01_ROOT_CAUSE=UNKNOWN
EPG01_XML_SOURCE_VERIFIED=NO
EPG01_TVH_MAPPING_AUDITED=NO
EPG01_KODI_PVRHTS_MAPPING_AUDITED=NO
EPG01_FIX_IMPLEMENTED=NO
```

## 7. Riesgos y límites que deben seguir vigentes

- Sin escribir ni borrar la DB SQLite Kodi `TVxx.db`; no reset de PVR, no reinicio periódico `pvr.hts`, no reenumerar canales a ciegas.
- Grupos protegidos Tvheadend intocables; sin toggles manuales de bouquets para provocar cambios. Mantener `autoname=True`.
- No construir/instalar binario CoreELEC sin revisar antes su build real; no ejecutar binario host en el hardware destino sin cross-compilar.
- Configuración de la instancia original en Docker **nunca** compartida en escritura con otra instancia; puertos distintos, respaldo y rollback.
- No compartir PCAP binarios, secretos de HTTP/M3U, credenciales HTSP ni tokens en logs.
- No confundir `git apply`/compilación PASS con hot-update funcional PASS.

## 8. Referencias dentro del repositorio

- `docs/HANDOFF_PVR_G3W_TO_G3AC_2026-11-21.md`: cronología completa y todos los gates G3-W…G3-AL.
- `docs/PVR_G3AB_CUID_NATIVE_LAB_2026-11-21.md`: laboratorio de identidad y escenarios.
- `docs/PVR_G3AC_HOT_REFRESH_AUDIT_2026-11-21.md`: pruebas de refresco.
- `docs/PVR_G3AH_HTSP_PCAP_DECODER_2026-11-21.md`: protocolo, parser PCAP/HTSP y tests.
- `docs/PVR_G3AK_TVH_CHANNEL_NOTIFY_DESIGN_2026-11-21.md`: análisis de causa y diseño.
- `docs/PVR_G3AL_TVH_PATCH_CANDIDATE_2026-11-21.md`: patch experimental, instrucciones y gates.
- `lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch`: diff del servidor sin desplegar.
- `tools/pvr_g3ah_htsp_pcap.py` y `tests/test_pvr_g3ah_htsp_pcap.py`: analizador y 12 pruebas.

## 9. Texto sugerido para iniciar el próximo chat

> Continuamos el proyecto masQelec `service.cloud.masqelec` en rama `develop`. Lee primero `service.cloud.masqelec/docs/HANDOFF_TVH_CUSTOM_CORELEC_EPG_2026-11-21.md` y el handoff G3-W→G3-AL. Hemos probado en G3-AH que TVH no notificó rename M3U sobre conexión HTSP existente en la ventana capturada y que dos reconexiones sí entregaron `channelAdd` + `initialSyncCompleted` (12/12 tests Ubuntu PASS). Parche `tvheadend-8837853a6-g3al-channel-notify.patch` aplicado a checkout upstream aislado, `make -j2` PASS en Ubuntu, NO probado en runtime. Próximo gate G3-AM: `file/ldd/--version`, preparar segundo TVH aislado y ensayo de `channelUpdate` sin reconexión, preservar IDs y grupos. **Tengo entorno de build CoreELEC preparado** para compilar luego versión personalizada; no asumir ruta ni arquitectura ni tocar master sin permiso. Tras corregir PVR, investigar EPG-01: géneros de guía siempre salen «Otros»/«Desconocidos»; causa XML/TVH/HTSP/Kodi todavía no diagnosticada. Documentar y commitear cada gate, sin dar por probado lo pendiente.
