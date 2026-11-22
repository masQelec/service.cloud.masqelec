# HANDOFF — IPTV/PVR CUID: G3-AS PASS → G3-AT (22/11/2026)

## 0. Instrucción de entrada para el próximo chat
Continuar el desarrollo y auditoría de Tvheadend modificado para mantener la identidad IPTV por `CUID` y evitar pérdida/duplicación de canales en Kodi durante actualizaciones de playlists. **El gate G3-AS está aprobado con SQLite real de Kodi.** Próxima fase **G3-AT: reordenación, altas, bajas y reaparición** de canales sintéticos y su efecto en Tvheadend/HTSP/Kodi. **NO construir para CoreELEC ni desplegar** hasta completar los gates de seguridad, regresión y compatibilidad. Leer este handoff y el diario [PVR_G3AN_CUID_SOURCE_CANDIDATE_2026-11-22.md](PVR_G3AN_CUID_SOURCE_CANDIDATE_2026-11-22.md) antes de ejecutar cambios.

## 1. Objetivo técnico y origen del fallo
- Tvheadend upstream (fuente exacta `8837853a6`) emparejaba muxes IPTV automáticos por URL normalizada. Cambiar solo el parámetro de la URL, incluso conservando identidad de canal en el proveedor, sustituía mux, servicio y canal TVH; en G3-AM Kodi cambió `iUniqueId=1699146942` a `354983035`. Esto rompe la continuidad de la biblioteca PVR.
- Solución G3-AN: propiedad persistible `mm_iptv_cuid` en mux IPTV, emparejamiento preferente por CUID y actualización de la URL sin reconstrucción del mux ni de sus servicios. Validaciones de CUID, adopción limitada de mux antiguo sin CUID y rechazo de asociaciones ambiguas. Requiere **auditoría negativa completa** antes de considerar el código final.
- Corrección G3-AO: una suscripción `epggrab` puede dejar el mux `mm_active` incluso sin datos. El parche permite modificar **solo la URL configurada** durante reproducción activa, porque el lector IPTV captura `mm_iptv_url_raw` al iniciar conexión; no fuerza desconexión ni sustituye servicio/canal.
- G3-AL previo mantiene notificaciones efectivas HTSP de renombrado. No reaplicar parches no idempotentes a fuentes ya parcheadas.
- CUID debe ser identidad estable de cada canal en playlist. No equiparar renombrados, orden, número o URL con identidad. Un cambio de URL con CUID igual debe conservar UUID; altas/bajas exigen protocolo explícito.

## 2. Forma de trabajo acordada
1. **Un único laboratorio modificable:** G3-AN y, para fuente sintética continua, G3-AP. G3-AB y G3-AM son referencias forenses **inmutables**. No reiniciar/modificar sus contenedores, redes, fixtures, config ni sus Kodi/TVH. No tocar producción ni binarios CoreELEC.
2. Repo conectado GitHub **`masQelec/service.cloud.masqelec`**, rama **`develop`**, ruta local `/home/ubuntu/GitHub/service.cloud.masqelec`; raíz de addon `service.cloud.masqelec/`. Trabajo en `develop` y documentación/commits por gate; operador ejecuta comandos Ubuntu y pega evidencias; asistente modifica código/docs en GitHub. `git pull --ff-only origin develop` antes de ejecutar herramientas nuevas.
3. Ciclo: inspección de fuente y estado real → análisis/hipótesis → preflight sólo lectura → cambios pequeños con guardas → `git diff --check`/sintaxis → prueba acotada → comparación exacta de identidades/bytes/SQLite → gate PASS/FAIL/INCONCLUSIVE → documentación y próxima acción. **Nunca inferir PASS sin la salida del operador.**
4. Todo comando con rutas concretas y filtros de scope; respaldos previos a mutaciones; no restaurar/resetear ni `docker compose down` globalmente. No usar `--portable` para Kodi: su wrapper dirige datos a instalación. Usar variables `KODI_DATA` + `HOME`/XDG aisladas.
5. Distinguir **URL de configuración cambiada sin cortar reproducción** de **cambio físico de fuente activa**: solo lo primero está demostrado. Distinguir identidad HTSP y SQLite inicial de supervivencia tras cambios sustanciales de lista.
6. No ejecutar `make install`; no sobrescribir `tvheadend-g3al-upstream`, el binario de G3-AM ni TV46.db a mano. No reejecutar helpers de parche G3-AN/G3-AO sobre fuente ya modificada: no idempotentes.
7. Configuración G3-AN usa `--noacl` **solo** en el entorno aislado; prohibido en producción. Las advertencias sobre `scanfile` no invalidaron los ensayos IPTV.

## 3. Repositorios, árbol fuente, red y procesos
- Repositorio GitHub: `masQelec/service.cloud.masqelec` → `develop`. Documentación acumulativa: `service.cloud.masqelec/docs/PVR_G3AN_CUID_SOURCE_CANDIDATE_2026-11-22.md` (larga, con cronología).
- Fuente TVH G3-AN: `/home/ubuntu/tvheadend-g3an-upstream`, upstream `8837853a6`, código IPTV en `src/input/mpegts/iptv/{iptv_auto.c,iptv_mux.c,iptv_private.h}`. Ejecutable `build.linux/tvheadend`. Configuración compilación Ubuntu de laboratorio deshabilita FFmpeg integrado, libav, documentación y tvhcsa si falta dvbcsa; se superaron fallos previos de dependencias/webui, compilando TVH G3-AN. Las correcciones están en el diario.
- Helpers de fuente: `service.cloud.masqelec/tools/pvr_g3an_apply_cuid_lab.py`, `.../pvr_g3ao_allow_active_url_refresh_lab.py`.
- Compose TVH: `service.cloud.masqelec/lab/pvr_g3ab/g3an/compose.yaml`; servicios `masqelec-pvr-g3an-tvh-1` y `masqelec-pvr-g3an-playlist-1`. TVH HTTP **`127.0.0.1:39991`**, HTSP **`127.0.0.1:39992`**. URL M3U interna `http://g3an-playlist/playlist.m3u`. Refetch cada minuto (`refetch_period=1`). Persistencia TVH en `service.cloud.masqelec/lab/pvr_g3ab/runtime/g3an/tvh_config` (solo G3-AN).
- Playlist privada: `service.cloud.masqelec/lab/pvr_g3ab/runtime/g3an/playlist/playlist.m3u`. Generador con guardas `service.cloud.masqelec/lab/pvr_g3ab/g3an/prepare.py` estados `init|baseline|url|live|live-url`. **Estado ACTUAL: `live`** (Alpha `http://g3ap-live:8080/ch1.ts`, Beta `http://streams/ch2.ts`, CUID `g3an-001`/`g3an-002`). No modificar generador original ciegamente: inspeccionar código actual, ampliar para G3-AT con nuevos estados y pruebas automatizadas.
- Fuente continua G3-AP: `service.cloud.masqelec/lab/pvr_g3ab/g3ap/{server.py,compose.yaml,Dockerfile}`. Servicio `masqelec-pvr-g3ap-live-1`, alias Docker `g3ap-live`, puerto interno 8080. `compose.yaml` usa imagen local `lscr.io/linuxserver/tvheadend:latest` con `pull_policy: never`, Python 3.12 y FFmpeg instalados y `entrypoint` Python directo; **no usar `docker compose build`**: Dockerfile inicial es candidato histórico que dependía de Docker Hub y falló DNS. `server.py`: HTTP ThreadingHTTPServer, rutas fijas `/ch1.ts`, `/ch2.ts`, `/healthz`, FFmpeg `-re -stream_loop -1 -c copy -f mpegts pipe:1`, máximo 6 clientes. Fuente `../runtime/streams:/source:ro` (original G3-AB montado SOLO lectura), se conserva sin modificar.
- Red Docker compartida `masqelec-pvr-g3ab_pvr_g3ab`. El `streams` original `masqelec-pvr-g3ab-streams-1` no se toca. G3-AM original `masqelec-pvr-g3am-tvh-1` se mantuvo vivo durante pruebas.
- Perfil Kodi **solo laboratorio**: `/tmp/g3ar-kodi-A3FZBaXx`, datos `data/userdata/Database/TV46.db`, log `data/temp/kodi.log`, baseline de retención `g3as-before.json`. Estas rutas son temporales y pueden desaparecer tras reinicio del Ubuntu: **verificar existencia antes de seguir**. Perfil real `$HOME/.kodi` existe y está fuera de alcance. Para lanzar Kodi aislado: `env -u KODI_HOME HOME="$LAB/home" KODI_DATA="$LAB/data" XDG_CONFIG_HOME="$LAB/config" XDG_CACHE_HOME="$LAB/cache" kodi --windowing=wayland`. No usar `timeout` si se requiere interacción prolongada; en ensayo boot anterior se cerraba a los 30 s deliberadamente.
- Kodi instalado Ubuntu **21.3** Debian `2:21.3+dfsg-1ubuntu1`, pvr.hts **21.2.6**, binario `/usr/lib/x86_64-linux-gnu/kodi/addons/pvr.hts/pvr.hts.so`; GUI Wayland `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, `XDG_RUNTIME_DIR=/run/user/1000`. Ajustes `pvr.hts` para G3-AN: `host=127.0.0.1`, `htsp_port=39992`, `http_port=39991`, `https=false`, `streaming_http=false`. Laboratorio `--noacl`: credenciales vacías. Primer intento del addon al puerto por defecto `9982` falló, tras configurarlo recreó cliente y conectó: no confundir el primer error de log con estado final.

## 4. Identidades de referencia — NO REGENERAR
| Objeto | Alpha | Beta |
|---|---|---|
| CUID | `g3an-001` | `g3an-002` |
| Mux UUID TVH | `afa32f8f8223bdff59057f7790448c92` | `c96721109b182b2d53fbba80bdc5820c` |
| Canal UUID TVH/HTSP `channelIdStr` | `e4852534cdb2fd64f54fd861d4d00767` | `0d3bd243f67184e9adb9ceadf4a51c50` |
| Servicio UUID | `4bfccf27c63505a1b6b81aec861174ed` | `0588b5c02d512b7045c254cf95ed46ab` |
| `channelId` HTSP / `iUniqueId` Kodi | `874874340` | `1137851149` |
| `idChannel` Kodi | `1` | `2` |
| `idEpg` Kodi | `1` | `2` |
| número TVH/Kodi | 1 | 2 |

Existía un tercer servicio TVH sin vincular a canal, UUID `923fc082cf4b92edf42d4b5a87da125e` (nombre `G3AN Beta`). Baseline **2 muxes, 3 servicios, 2 canales**, no inventar que solo existen dos servicios. Network UUID `d1642fb49f8bf0d2c583ce1b2deae146`; `/tmp/g3an-baseline-identity.json` sirve de snapshot de UUID si persiste en host. En disco TVH guarda configuración en **HTSMSG2 comprimido gzip** (`b'\\xff\\xffGZIP01'` y longitud big endian bytes 8:12, payload gzip desde byte 12); `grep` sobre comprimido **no** demuestra ausencia de CUID.
TVH normaliza guiones bajos en query como `%5F`; comparar URLs mediante `urllib.parse.urlsplit` + `parse_qsl` semánticamente, no cadenas crudas.

## 5. Pruebas/gates con evidencias recibidas
| Gate | Resultado | Evidencia concreta |
|---|---|---|
| G3-AN CUID | PASS | Parches de fuente aplicados/compilados; CUID visible en API y disco comprimido; tras reinicio mux/servicio/canal UUID y CUID conservados |
| G3-AO | PASS | Cambio de URL configurada con mux activo sin recrear identidades; `G3AO_FINAL_GATE=PASS`; posteridad del HTTP confirmada |
| G3-AP preflight | PASS | `ffprobe`: fuente original MPEG2+MP2, 12.010023 s, 1,037,948 B. Re-mux 36.106756 s, 3,123,808 B, sin errores observados |
| G3-AP Docker offline | PASS | DNS Docker Hub falló; imagen local LinuxServer trae FFmpeg+Python; Compose cambiado a `pull_policy:never`; contenedor /healthz OK después de carrera de arranque |
| G3-AP HTTP | PASS | 200 `video/mp2t`; bytes a 10/20/30/40 s: 899204/1805176/2673360/3557148 |
| G3-AP TVH cutover | PASS | Alpha a `http://g3ap-live:8080/ch1.ts`; UUID de muxes, servicios, canales y ambos CUID conservaron identidad; Beta URL igual |
| G3-AP reproducción TVH | PASS | `/stream/channel/<Alpha-UUID>` 200, `video/mp2t`, 1,791,076 B en 20 s; curl código 28 por timeout planificado con datos |
| G3-AO active stream URL | PASS | En plena descarga, `live`→`live-url`; cliente siguió vivo sin error, +1,270,880 B tras detectar URL nueva, UUID/CUID estables. Mismo servidor, cambia query; NO demuestra cambio físico de origen |
| G3-AQ HTSP | PASS | HTSP v44; en dos conexiones 2 canales con `channelIdStr` y `channelId` idénticos; herramienta read-only `tools/pvr_g3aq_htsp_identity_probe.py` |
| G3-AQ reinicio TVH | PASS | `docker restart --time 10 masqelec-pvr-g3an-tvh-1`; `G3AQ_HTSP_RESTART_PERSISTENCE=PASS`, IDs sin cambios, G3-AM intacto |
| G3-AR Kodi primer import | PASS | TV46.db muestra 2 canales, 1 cliente `pvr.hts`, `iUniqueId` idénticos a HTSP `channelId`, `idChannel` 1 y 2, sin duplicación inicial |
| G3-AS Kodi tras cambio | **PASS** | Con Kodi de laboratorio abierto: `G3AS_PREFLIGHT=PASS`, `prepare.py live` sobre G3-AN, comprobados ambos mux UUID/CUID y URL Alpha nueva. Cerrado Kodi, comparación TV46.db vs `g3as-before.json`: `TWO_CHANNELS=True`, `NO_DUPLICATES=True`, `EXPECTED_IDS=True`, `RECORDS_STABLE=True`, `PVR_CLIENT_STABLE=True`, `G3AS_KODI_RETENTION=PASS`. Cliente `[(1, 'pvr.hts', 1)]`. |
| G3-AT | **PENDIENTE** | Reordenación, alta Gamma, baja Gamma, reaparición, sincronización y huérfanos en Kodi |
| CoreELEC | **NO AUTORIZADO** | Build nativo aún no efectuado, evitar mezclar experimentos de Ubuntu y despliegue real |

El log de TVH al apagar listaba `mpegts ... deleting` pero tras reiniciar los UUID HTSP fueron idénticos, por lo que no implica pérdida de identidad. Los mensajes sobre `scanfile` tampoco invalidaron el lab. El snapshot SQLite G3-AS verifica registros de canal idénticos; **no se obligó a Kodi a refrescar metadatos si el contenido del canal no cambiaba**, algo que sería normal en este escenario.

## 6. Situación EXACTA al cerrar el chat
- Rama `develop`; último commit GitHub antes de este handoff: `67d06c97c3f81c672ce5543528539663cd0346f1`, que añadió resultado `G3AS_KODI_RETENTION=PASS` al diario. Al crear este documento cambiará HEAD: obtener nuevo SHA.
- Playlist G3-AN **`live`**, Alpha `http://g3ap-live:8080/ch1.ts`; Beta `http://streams/ch2.ts`; 2 CUID estables. La última modificación de lista fue `live-url` → `live` en G3-AS.
- Kodi de laboratorio se cerró antes de auditoría SQLite; sin evidencia de proceso en ejecución tras ella. G3-AN y G3-AP habían funcionado; estado actual del Docker debe volver a comprobarse con `docker ps`, no darlo por vivo indefinidamente.
- `TV46.db` laboratorio y baseline `g3as-before.json` estaban disponibles en `/tmp/g3ar-kodi-A3FZBaXx/` durante el último gate; confirmar antes de G3-AT.
- No se ha hecho ningún cambio G3-AT. El generador actual solo soporta dos canales: para probar alta/baja/reordenación habrá que ampliar *solo* el generador G3-AN con etapas explícitas y guardas, sin tocar la playlist de G3-AB.
- El usuario prefiere pasos reproducibles, auditoría técnica crítica, commits/documentación por gate, y que el asistente no invente ni adelante resultados. No repetir trabajo ya superado salvo revalidaciones justificadas.

## 7. Plan G3-AT por gates, con guardas y rollback
**Primero: preflight de solo lectura y backups verificables, aún no mutar.**
1. `git -C /home/ubuntu/GitHub/service.cloud.masqelec status --short` y `git pull --ff-only origin develop`; comprobar docker `ps` de G3-AN, G3-AP, G3-AM y G3-AB y TCP 39991/39992.
2. Confirmar perfil Kodi de lab existente y **Kodi no ejecutándose**, conservar `TV46.db` mediante `sqlite3.Connection.backup` a un archivo bajo el mismo lab o ubicación aislada; guardar hashes, filas channels/clients/grupos y baseline JSON (comparación de identidad por `iClientId,iUniqueId,idChannel`; asignación de grupos por `map_channelgroups_channels`). Nunca editar `TV46.db` a mano. Respaldar **solo** playlist/config del G3-AN antes de cambios: snapshots de `runtime/g3an/playlist/playlist.m3u` y `runtime/g3an/tvh_config` aislados con control de propietario, enlaces y rutas, sin sobrescribir otros datos. No manipular configs TVH mientras está activo; copiar snapshots para recuperación, no restaurar en caliente.
3. Inspeccionar en código fuente TVH las reglas exactas de eliminación en `iptv_auto.c`, `iptv_mux.c`, red IPTV Auto, `remove_args`, `remove_old`/servicios y su correspondencia con HTSP `channelDelete`; **no asumir** que borrar línea M3U elimina canal en Kodi. Diseñar evidencia del efecto real, y definir si el resultado esperado es eliminación o retención intencionada.
4. Extender `g3an/prepare.py` con etapas sintéticas explícitas (`reorder`, `add-gamma`, `remove-gamma`, `readd-gamma`, quizá `restore-live`), sin manipulación de CUID actuales. Preservar URLs y fuentes de Alpha/Beta. No reutilizar `g3an-001` ni `g3an-002` para otro canal. Gamma con `g3an-003`, URL viable tras comprobar emisor; preparar `ch3.ts` G3-AN específico si hace falta, **sin tocar fixtures de G3-AB**. `g3ap/server.py` actualmente solo admite `/ch1.ts` y `/ch2.ts`, no inventar `/ch3.ts`.
5. **Reordenación** Alpha/Beta: comparar ID HTSP y tablas SQLite *antes/después* de una sincronización real, verificar el orden y números contra expectativa sin cambiar `iUniqueId` ni `idChannel`; no confundir orden de líneas de la lista con número definido `tvg-chno/tvh-chnum`. Si se desea cambiar números, convertirlo en gate separado.
6. **Alta Gamma**: observar mux/service/channel creados, CUID único, HTSP `channelAdd`, Kodi `iUniqueId` nuevo, dos registros antiguos intactos; determinar si el map automático servicios↔canales requiere habilitar algo adicional en TVH.
7. **Baja Gamma**: evaluar política de eliminación en TVH, posibles servicios huérfanos y si Kodi recibe `channelDelete`; medir latencia y comprobar SQLite tras cierre limpio. Reaparición: definir si se espera recuperar ID (depende de política de borrado), registrar el comportamiento sin imponer una expectativa no sustentada. Probar escenarios de CUID duplicado o ausente de modo controlado.
8. Registrar stdout y hashes, cambios de IDs/contadores y rollback/recuperación por gate. No automatizar eliminación de canales reales ni abrir CoreELEC hasta gates completos.

## 8. Comandos útiles y diagnóstico SIN mutaciones
```bash
REPO=/home/ubuntu/GitHub/service.cloud.masqelec
ROOT="$REPO/service.cloud.masqelec"
git -C "$REPO" status --short
git -C "$REPO" log -1 --oneline
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'masqelec-pvr-g3a'
python3 "$ROOT/tools/pvr_g3aq_htsp_identity_probe.py"
curl -fsS 'http://127.0.0.1:39991/api/mpegts/mux/grid' | python3 -m json.tool | head -90
test -f '/tmp/g3ar-kodi-A3FZBaXx/data/userdata/Database/TV46.db' && echo G3AT_KODI_DB=EXISTS
test -f '/tmp/g3ar-kodi-A3FZBaXx/g3as-before.json' && echo G3AT_BASELINE=EXISTS
pgrep -ax kodi.bin || :
```
**Aviso:** `head` tras `curl` podría cortar tubería cuando el JSON sea muy grande; es una inspección no un gate. Si `git status` no está limpio, inspeccionar antes de pull o cambios. No confiar en `/tmp` tras reboot.

## 9. Documentos/herramientas relevantes
- Diario técnico completo: `docs/PVR_G3AN_CUID_SOURCE_CANDIDATE_2026-11-22.md`.
- Este handoff: `docs/HANDOFF_PVR_G3AS_PASS_NEXT_G3AT_2026-11-22.md`.
- Parches fuente: `tools/pvr_g3an_apply_cuid_lab.py` (no idempotente), `tools/pvr_g3ao_allow_active_url_refresh_lab.py` (no idempotente).
- HTSP read-only: `tools/pvr_g3aq_htsp_identity_probe.py`.
- Playlist generador: `lab/pvr_g3ab/g3an/prepare.py`.
- G3-AN TVH compose: `lab/pvr_g3ab/g3an/compose.yaml`.
- G3-AP continua: `lab/pvr_g3ab/g3ap/server.py`, `compose.yaml`.
- G3-AB/G3-AM docs y sus ficheros son referencias forenses. Evitar operaciones sobre ellos.

## 10. Próxima acción recomendada al abrir chat
**NO hacer cambio de lista directamente.** Comenzar con lectura de este handoff y diario, auditoría de `iptv_auto.c` respecto a bajas y mapa de canales, inventario de respaldos/runtime `G3AT_PREFLIGHT` y diseño de etapas de playlist sin romper CUID. Primera ejecución debería ser inspección de estado y respaldo verificable del *perfil Kodi aislado* y de la configuración G3-AN. Después añadir tests negativos y estados del generador en GitHub, validar preflight con operador y avanzar gate por gate.

## 11. Regla de cierre de gates
Los marcadores `PASS` reflejan exclusivamente salidas verificadas en esta conversación. No son certificación de producción. Para CoreELEC hay build nativo preparado por el usuario, **pero no se ha utilizado**; se hará tras completar la adaptación, pruebas negativas y regresión de Tvheadend y PVR. Pendiente además la futura investigación de EPG: géneros que aparecen como `Otros/Desconocidos` al leer XMLTV. Es un objetivo **posterior** a los gates de identidad/mantenimiento; no mezclar cambios EPG en esta rama de ensayos.
