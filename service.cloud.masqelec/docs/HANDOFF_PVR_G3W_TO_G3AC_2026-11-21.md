# HANDOFF PVR G3-W → G3-AC — Mantenimiento PVR nativo (2026-11-21)

**Proyecto**: `masQelec/service.cloud.masqelec`, rama `develop`. **Ruta repo**: `service.cloud.masqelec/`. **Ruta Ubuntu**: `/home/ubuntu/GitHub/service.cloud.masqelec`. Este documento es el punto de entrada para continuar en otro chat; leer los informes detallados enumerados abajo y el código fuente antes de alterar el proyecto.

## Objetivo funcional y límites

El addon gestiona la playlist M3U y el mantenimiento PVR (Tvheadend + Kodi, cliente `pvr.hts`). El sistema heredado en `lib/update_pvr.py` realiza acciones potencialmente destructivas: reconciliación por nombre contra base de datos Kodi TVxx.db, baja Tvheadend por API, reinicios/alternancia PVR y mantenimiento de tags. Objetivo: **mantener el inventario de canales y grupos correctamente y refrescar Kodi a través de interfaces nativas, sin escrituras SQLite, sin bajas ambiguas y preservando la identidad cuando sea posible**.

Restricciones:
- Master CoreELEC `root@192.168.1.102`: **sin escritura, despliegue ni ensayo destructivo autorizado**. No probar cambios de URL/playlist, ni deshabilitar PVR ni borrar canales/grupos en master.
- Los seis grupos históricos extra de Tvheadend están protegidos; playlist histórica: 720 canales, 26 grupos, TVH 32 tags, 24 nombres duplicados. Las observaciones son históricas: la M3U publicada en `masQelec/cloud.masqelec/pvr/playlist.m3u` tenía **865** `#EXTINF` y **865 CUID únicos** al consultarla el 21/11/2026. No equiparar épocas ni afirmar divergencia de producción sin medir ambos inventarios al mismo tiempo.
- No activar `CUTOVER`, no sustituir `update_pvr.py`, no eliminar mecanismos de recuperación antes de gates completos. No manipular directamente `TVxx.db` durante laboratorios.
- Nunca interpretar `CUID` como identificador TVH/HTSP demostrado. Los CUID observados en M3U son valores textuales opacos y la API TVH no mostró mapeo CUID→UUID.

## Entornos

- Master: CoreELEC Kodi **21.2.5** (`Amlogic-ng.arm`), `pvr.hts 21.2.6.1`. Ubuntu laboratorio Kodi **21.3**, `kodi-pvr-hts 21.2.6+ds-1.1`. La equivalencia de comportamiento/binarios **NO** está demostrada.
- G3-W: `lab/pvr_g3w/`; Compose `masqelec-pvr-g3w`, TVH HTTP `127.0.0.1:19981`, HTSP `127.0.0.1:19982`; playlist sintética sin CUID, generador `prepare.py before|added|removed`. **No alterar este runtime para G3-AB**.
- G3-AB: `lab/pvr_g3ab/`; Compose `masqelec-pvr-g3ab`, TVH HTTP **`127.0.0.1:19991`**, HTSP **`127.0.0.1:19992`**; `runtime/playlist/playlist.m3u`, `runtime/tvh_config`, `runtime/streams`, `runtime/kodi_home`. Generador `prepare.py baseline|rename|url|group|reorder|homonym|restored`. Todos los estados tienen CUID `g3ab-001`, `g3ab-002`. Al pasar de una etapa a otra, **cada etapa se construye desde baseline**: no pasar `rename → url` sin restauración, o se cambian dos atributos. Los contenedores se iniciaron con puertos limitados a loopback. Kodi G3-AB se ejecuta desde Ubuntu con `HOME="$PWD/runtime/kodi_home" kodi`; no abrir simultáneamente G3-W y G3-AB Kodi. El socket del proceso Kodi se verificó ESTAB a `127.0.0.1:19992`; JSON-RPC se consultó en `127.0.0.1:8080` (ojo: antes se vio escucha `0.0.0.0:8080`; evitar exposición LAN).
- Los flujos TS de laboratorio son **12 segundos** generados por ffmpeg, servidos por Nginx en red Docker; no son evidencia de reproducción continua.

## Fases y evidencias confirmadas por operador

| Fase | Resultado real | Conclusión precisa |
| --- | --- | --- |
| G3-W | TVH y Kodi **2→3→2** con IDs originales estables | Kodi Ubuntu retiró el canal desaparecido sin escritura SQLite solicitada, no acredita CoreELEC |
| G3-X | 16 tests PASS | Shadow read-only `lib/pvr_native_convergence.py`, no reemplazo del legado; rechaza ambigüedad por homónimos |
| G3-Y | 17 tests PASS | TVH `uuid` y Kodi `channelid` visibles, **sin puente probado** CUID/HTSP |
| G3-Z | 10 tests PASS | Referencias a servicios son `str`; sin resolución todavía |
| G3-Z2 | 13 tests PASS; 2 referencias de canal resueltas entre 3 servicios | Integridad TVH canal→servicio sin CUID |
| G3-Z3–Z5 | 1 servicio sin canal/deshabilitado, comparte mux con servicio de canal | No borrar servicios/muxes por no estar asociados |
| G3-AA | 15 tests PASS | Comparador offline por CUID seguro ante nombres duplicados/cambios, sin demostrar soporte CUID por TVH |
| G3-AB | Compose y playlist sintética en Ubuntu; 2 canales estables tras duplicado Beta temporal; fuente de duplicado **no demostrada** | Baseline TVH/Kodi establecido |
| G3-AB rename | Tvheadend cambia nombre conservando UUID de canal; Kodi mantiene ID pero **no** refresca etiqueta en caliente durante observación; al reiniciar Kodi una vez la actualiza | Mecanismo de refresco en vivo NO validado |
| G3-AB restored | TVH vuelve a nombre inicial; Kodi no refresca en caliente, **reiniciar PVR dentro de Kodi** sí actualiza nombre manteniendo ID | Tipo exacto de acción de reinicio PVR operador no precisado; no automatizar en producción |
| G3-AB URL | Nueva URL `ch1-alt.ts` aplicada; Tvheadend **sustituye UUID de canal/servicio/mux de Alpha**, Beta estable | CUID estable en playlist **no conserva identidad TVH** ante URL |
| G3-AB Kodi URL | Tras refresco manual PVR, Kodi mantiene Alpha `channelid=2` y Beta `1` | NO demuestra por sí solo continuidad backend, pero TVH registra suscripción de Alpha |
| G3-AB suscripción | TVH `status/subscriptions`: Alpha `Running`, errors=0, entrada/salida >0 | El flujo se entrega por TVH; imagen/audio perceptibles en GUI Kodi **no confirmados** |
| G3-AC | **9/9 tests PASS**, tres snapshots `NAMES_MATCH=true`, `ID_PRESERVED=true` | Sistema actualmente convergido; **no se provocaron cambios entre snapshots**, por tanto **NO prueba refresco en caliente** |

### Identidades concretas del laboratorio G3-AB

Baseline antes de URL:
- TVH Alpha canal `185e5bdda6aafa6aa1aad2bb94ee703a`; servicio `18cd0031a734c2342ac3956d754fb63e`; mux `4d3f4f0b654e570dc39029bebaf5c555`; Kodi Alpha `channelid=2`.
- TVH Beta canal `f08f75aa26b58386630d4b225adbb34f`; servicio `afe6f317e9b95eb03f6d91691e80f537`; mux `355a43f5f4c718478b87d3b6a1bc8408`; Kodi Beta `channelid=1`.

Tras cambio `url` de Alpha:
- TVH Alpha canal **`780608ad2385d70c9d46279e0f62250e`**; servicio **`5a6962a3ab51cfec0c933f6cc7eda030`**; mux **`f9e55f38b435969d396393edc3b7acc4`**; campo `iptv_url` coincide con `http://streams/ch1-alt.ts`.
- Beta mantuvo sus tres UUID.
- Kodi tras reinicio/refresco PVR: Alpha `channelid=2`, Beta `1`, sin duplicados.
- TVH demostró suscripción de Alpha `Running` con `errors=0`, `total_in=965192`, `total_out=881587`. `status/subscriptions.service` contiene nombre descriptivo, **no** UUID.

G3-AC observaciones finales (operador): 9 tests unitarios en 0.000s OK, tres lecturas cada una `TVH_COUNT=2`, `KODI_COUNT=2`, `NAMES_MATCH=true`, `ID_PRESERVED=true`, `TVH_NAMES=[G3AB Alpha,G3AB Beta]`, `KODI_NAMES` iguales, `HTSP_EVENT_SEEN=NOT_MEASURED`, `KODI_TRIGGER_SEEN=NOT_MEASURED`, `CUID_MAPPING_PROVEN=false`, `SQLITE_TOUCHED=false`. **Puede ser solo la convergencia actual de etiquetas: no inventar que una actualización HTSP fue vista.** La etapa efectiva del fichero M3U después de ensayos previos debe comprobarse antes de futuros cambios.

## Auditoría fuente pvr.hts Omega: mecanismo nativo ya existe

Se inspeccionó **directamente** `kodi-pvr/pvr.hts` rama `Omega`, archivo https://github.com/kodi-pvr/pvr.hts/blob/Omega/src/Tvheadend.cpp :
- `AsyncProcess()` en torno a líneas 1738–1744 acepta `channelAdd`, `channelUpdate`, `channelDelete`; `channelUpdate` llama `ParseChannelAddOrUpdate(msg,false)`.
- `ParseChannelAddOrUpdate()` en torno a líneas 2129–2220 lee `channelId`, actualiza `channelName` si está en el mensaje, compara objeto anterior y posterior y llama `TriggerChannelUpdate()` si cambió y ya superó `ASYNC_CHN`.
- La cola de eventos `HTSP_EVENT_CHN_UPDATE` se procesa fuera del mutex y llama a `kodi::addon::CInstancePVRClient::TriggerChannelUpdate()` (~1834).
- `GetChannels` (~336–372) entrega `SetUniqueId(channel.GetId())` y `SetChannelName(channel.GetName())`. **`CUID` de playlist no forma parte de este mapeo.**
- Esta es evidencia del **código Omega de referencia**, no del binario exacto compilado `21.2.6.1` en CoreELEC.
- Faltan evidencias de emisión del evento desde el servidor, recepción en el cliente, activación del callback, y reacción de Kodi. No atribuir el fallo a capa específica sin instrumentación.
- La API JSON-RPC pública no ofrece una llamada `PVR.UpdateChannels` documentada; `PVR.Scan` no significa refrescar metadatos.

## Archivos y documentos a leer al retomar

Código:
- `lib/update_pvr.py` (legado, sin migrar).
- `lib/pvr_native_convergence.py` (shadow sin mutación).
- `lib/pvr_cuid_offline.py`, `tests/test_pvr_cuid_offline.py` (comparador CUID; 15 PASS).
- `lab/pvr_g3w/prepare.py`, `lab/pvr_g3ab/prepare.py`, `lab/pvr_g3ab/compose.yaml` (laboratorios separados).
- `tools/pvr_g3ac_observe.py`, `tests/test_pvr_g3ac_observe.py` (9 PASS).

Documentos:
- `docs/PVR_G3W_ISOLATED_LAB_2026-11-21.md`.
- `docs/PVR_G3X_NATIVE_SHADOW_2026-11-21.md`.
- `docs/PVR_G3Y_IDENTITY_FIELDS_2026-11-21.md`.
- `docs/PVR_G3Z_TVH_SERVICE_SHAPES_2026-11-21.md`.
- `docs/PVR_G3Z2_SERVICE_RESOLUTION_2026-11-21.md`.
- `docs/PVR_G3AA_CUID_IDENTITY_2026-11-21.md`.
- `docs/PVR_G3AB_CUID_NATIVE_LAB_2026-11-21.md`.
- `docs/PVR_G3AC_HOT_REFRESH_AUDIT_2026-11-21.md`.

## Próximo trabajo — G3-AD (seguir en este chat o en otro)

**Prioridad del operador:** conseguir que **el cliente PVR se refresque en caliente**, sin reiniciar Kodi, sin ciclos automáticos de desactivar/re-activar `pvr.hts`, sin alterar SQLite, con mínimo impacto en reproducción.

1. Actualizar árbol local `git pull --ff-only origin develop`; comprobar `git status --short` y tests G3-AC.
2. Verificar **estado real actual** de M3U G3-AB (baseline/rename/url/restored) y TVH/Kodi sin asumir etapa por etiquetas actuales.
3. Identificar herramientas viables para observar en un ensayo controlado `channelUpdate` **en HTSP** y `TriggerChannelUpdate` **en cliente**. Priorizar logs Kodi/pvr.hts debug en perfil **aislado**, fuente exacta del addon/versión disponible; evitar modificar daemon de producción. La conexión HTSP transporta datos binarios y puede estar autenticada: no publicar capturas con tokens/sesiones; no confundir raw packet count con prueba de contenido `channelUpdate`.
4. Diseñar un ensayo **solo rename**, a partir de URL y metadatos restaurados, observar antes/durante/después el evento y `label` mientras cliente permanece conectado. El observador actual solo lee inventarios y **no** tiene instrumentación HTSP.
5. Clasificar dónde se interrumpe la cadena: emisión TVH, recepción pvr.hts, detección de cambio y callback Kodi, o aplicación final. Proponer solución mínima **solo cuando se demuestre la causa**. No asumir que addon Python puede llamar callbacks C++ de `pvr.hts`.
6. Si un cambio de URL sigue regenerando UUID de TVH, no diseñar limpieza por nombre ni asumir que CUID los preserva; establecer estrategia de equivalencia de identidad no destructiva o aceptar cambio controlado de identidad según garantías observadas.
7. Mantener comprobación de grupos protegidos (6 históricos), duplicados, cambios de nombre y URLs, y futuras pruebas CoreELEC **solo tras autorización**.

## Comandos seguros para retomar

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
git status --short
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ac_observe.py' -v
python3 service.cloud.masqelec/tools/pvr_g3ac_observe.py --samples 3 --interval 10
cd service.cloud.masqelec/lab/pvr_g3ab
docker compose ps
grep -E 'CUID=|ch1-alt' runtime/playlist/playlist.m3u | sed -E 's#https?://[^ ]+#<REDACTED_URL>#g'
```

No publicar M3U real, credenciales IPTV, tokens HTSP ni datos del master.

## Gates al cierre de este handoff

```text
G3W_NATIVE_2_3_2_UBUNTU=PASS_OBSERVED
G3AA_OFFLINE_CUID_UNIT=PASS_15
G3AB_TVH_RENAME_AND_RESTORE=PASS
G3AB_KODI_RENAME_REQUIRES_PVR_REFRESH=OBSERVED
G3AB_URL_NEW_TVH_CHANNEL_SERVICE_MUX=CONFIRMED
G3AB_URL_KODI_CHANNELIDS_AFTER_PVR_REFRESH=UNCHANGED_2_AND_1
G3AB_URL_TVH_SUBSCRIPTION_RUNNING_ZERO_ERRORS=PASS
G3AC_UNIT_TESTS=PASS_9
G3AC_LAB_SAMPLES=PASS_3_STATIC_MATCH
G3AC_HTSP_CHANNELUPDATE_CAPTURE=NOT_DONE
G3AC_KODI_NATIVE_TRIGGER_CAPTURE=NOT_DONE
G3AC_AUTO_HOT_REFRESH=NOT_PROVEN
CUID_TO_TVH_UUID_PROVEN=NO
CUID_TO_KODI_CHANNELID_PROVEN=NO
MASTER_MODIFIED=NO_REPORTED
SQLITE_MAINTENANCE_REMOVED=NO
PRODUCTION_CUTOVER_AUTHORIZED=NO
```

**No sustituir estas declaraciones por afirmaciones más fuertes sin nuevas mediciones.**


## G3-AD: inventario de log Kodi y estado M3U (operador, 2026-11-21)

Consulta read-only desde el perfil G3-AB:

```text
=== LABORATORIO ===
M3U_EXISTE: True
URL_ALTERNATIVA: True
NOMBRE_RENOMBRADO: False
=== KODI LOG ===
LOG_EXISTE: True
PVR_HTS_COUNT: 84
HTSP_COUNT: 22
CHANNEL_UPDATE_COUNT: 0
CHANNEL_ADD_DELETE_COUNT: 0
DEBUG_LINES_COUNT: 1
```

La M3U sigue en URL alternativa y **no** en la etapa `rename`. El log contiene referencias a cliente/HTSP pero ningún literal `channelUpdate` o `channelAdd`/`channelDelete`; el conteo `DEBUG_LINES_COUNT: 1` **no demuestra** cuál es el nivel de log efectivo ni si están habilitadas categorías PVR/cliente: se contó texto, no se verificó configuración. **No concluir ausencia de eventos HTSP** a partir de cero coincidencias textuales. Tampoco repetir un ensayo de renombrado sobre la etapa `url` sin restaurar primero la URL original para no mezclar cambios de atributos.

`G3AD_KODI_LOG_PRESENT=YES`, `G3AD_KODI_LOG_CHANNELUPDATE_LITERAL=0`, `G3AD_HTSP_EVENTS_OBSERVED=NO`, `G3AD_DEBUG_CAPABILITY=NOT_VERIFIED`, `G3AD_URL_VARIANT_ACTIVE=YES`. Próximo paso: inspeccionar configuración real de logging disponible en Kodi de laboratorio y preparar una captura de alcance limitado antes del cambio de nombre. No subir logs sin revisar posibles URLs, IPs, credenciales o tokens. No modificar master/SQLite.


## G3-AD: nueva medición de logs después de activar diagnóstico (operador, 2026-11-21)

```text
LOG_LINES: 606
LOG_BYTES: 71353
DEBUG_LINES: 13
PVR_HTS_LINES: 84
CHANNEL_EVENTS_LINES: 0
TRIGGER_CHANNEL_UPDATE_LINES: 0
PVR_CHANNEL_LOGS_LINES: 3
```

Este conteo demuestra que existe `kodi.log` y contiene algunas líneas con el literal `DEBUG` y menciones `pvr.hts`, **no** que `pvr.hts` emita logs por cada notificación HTSP ni que el nivel de registro esté efectivamente habilitado para dichos eventos. Aún no se ha introducido un cambio de canal durante esta observación. `channelUpdate` y `TriggerChannelUpdate` no aparecen como cadenas; **no** implica que los eventos no se hayan producido o que la notificación HTSP esté rota.

`G3AD_LOG_LINES=606`, `G3AD_LOG_BYTES=71353`, `G3AD_DEBUG_LITERAL_LINES=13`, `G3AD_CHANNEL_EVENT_LITERALS=0`, `G3AD_EVENT_CAUSE=UNPROVEN`. Próximo control: identificar en el log, sin publicar líneas completas sensibles, si hay eventos recientes del addon al arrancar, y después ensayar un único renombrado con URL original previamente restaurada y snapshots TVH/Kodi, sin reiniciar PVR en medio. No modificar SQLite ni master. Si no hay telemetría explícita, distinguir siempre "no aparece en log" de "no se emitió".


## G3-AD: URL original del flujo Alpha restaurada realmente en TVH (operador 2026-11-21)

Después de `python3 prepare.py restored` en el fixture G3-AB, el operador consultó por GET `channel/grid`, `mpegts/service/grid` y `mpegts/mux/grid`:

```text
TVH_CANALES: 2
ALPHA_UNICO: True
ALPHA_SERVICIOS: 1
URL_ORIGINAL_RESTAURADA: True
```

**Resultado:** existen dos canales en el inventario y un único canal nominal Alpha, con una referencia de servicio y `iptv_url == http://streams/ch1.ts`. `G3AD_ALPHA_ORIGINAL_URL_TVH=PASS`; `G3AD_ALPHA_TVH_NAME_BASELINE=PASS`; `G3AD_KODI_BASELINE_AFTER_RESTORE=NOT_RECHECKED`; `G3AD_RENAME_EVENT_CAPTURE=NOT_STARTED`. No se ha medido si el UUID TVH original se recuperó; **no inferirlo** por el hecho de restaurar la URL. Siguiente paso: snapshot Kodi JSON-RPC de nombre, ID y número de canales, y verificar proceso cliente enlazado al HTSP 19992 antes de un cambio de nombre únicamente. La operación no debe reiniciar PVR ni leer/escribir Kodi TVxx.db durante el ensayo.


## G3-AD: gate de identidad Kodi FALLA tras restaurar URL (operador, 2026-11-21)

Snapshot de `PVR.GetChannels(channelgroupid=alltv)` en Kodi G3-AB después de `prepare.py restored` y verificación de URL original en TVH:

```text
ID: 3 NOMBRE: G3AB Alpha
ID: 2 NOMBRE: G3AB Beta
TOTAL: 2
BASELINE_CORRECTO: False
```

El baseline anterior de Kodi era Alpha `channelid=2`, Beta `channelid=1`. **Los DOS IDs JSON-RPC aumentaron en 1**, aunque el inventario muestra los mismos dos nombres y no duplicados. Antes de restaurar la URL, el último observador G3-AC había registrado `ID_PRESERVED=true` (Alpha 2, Beta 1). Este es el primer snapshot que documenta el cambio. No existe medición del instante exacto ni causa, ni prueba de cambio de instancia PVR, EPG, favoritos o grabaciones. **Importante:** `PVR.GetChannels.channelid` es el ID local presentado por Kodi, distinto de `PVRChannel.SetUniqueId(channel.GetId())` en pvr.hts, que representa el UID del backend HTSP; no comparar ambos como si fueran idénticos.

`G3AD_KODI_BASELINE_IDS_STABLE=FAIL`, `G3AD_KODI_ALPHA_ID_NOW=3`, `G3AD_KODI_BETA_ID_NOW=2`, `G3AD_KODI_TOTAL=2`, `G3AD_TVH_URL_ORIGINAL_RESTORED=YES`, `G3AD_RENAME_TRIAL=BLOCKED_PENDING_IDENTITY_DIAGNOSIS`. STOP a nuevos `prepare.py rename`, reinicios PVR o limpiezas mientras se determina si se trata de reconstrucción, nueva instancia PVR, o identidad del backend. Siguiente: snapshot de estabilidad de Kodi tras intervalo sin mutaciones, capturar UUID TVH actuales + servicios + mux, y registrar metadatos limitados de Kodi PVR de modo read-only. No consultar ni escribir TVxx.db. No inferir que el valor numérico +1 sea un desplazamiento sistemático.


## G3-AD CRÍTICO: IDs TVH Alpha y Beta sustituidos; Kodi muestra cero filas en 2 snapshots (2026-11-21)

El operador devolvió 2 de las 3 muestras del script de diagnóstico (tercera aún no recibida):

```text
=== MUESTRA 1 ===
TVH: G3AB Alpha UUID: dba29285ca808eb6486d364f994b05db
TVH: G3AB Beta UUID: 3bf90ae8eb828a6e4961902724a1f380
TOTAL_TVH: 2
TOTAL_KODI: 0
=== MUESTRA 2 ===
TVH: G3AB Alpha UUID: dba29285ca808eb6486d364f994b05db
TVH: G3AB Beta UUID: 3bf90ae8eb828a6e4961902724a1f380
TOTAL_TVH: 2
TOTAL_KODI: 0
```

Comparación: antes de restaurar M3U, Alpha UUID `780608ad2385d70c9d46279e0f62250e`, Beta `f08f75aa26b58386630d4b225adbb34f`; ambos UUID actuales difieren. La restauración a la URL original coincidió temporalmente con regeneración de ambos objetos, incluida Beta que no fue modificada deliberadamente. **Causalidad y momento exacto sin demostrar**. Dos observaciones confirman estabilidad de UUID TVH actuales, pero no identidad a largo plazo.

**BUG IMPORTANTE DEL SCRIPT DE DIAGNÓSTICO ANTERIOR**: se recuperaba Kodi con `read(KODI).get("result", {}).get("channels", [])` sin comprobar `error` JSON-RPC ni estructura `result`, por lo que `TOTAL_KODI: 0` puede ser respuesta JSON-RPC de error o resultado vacío. **No declarar que Kodi borró sus canales, ni que PVR está desconectado, hasta inspeccionar respuesta sanitizada.** El snapshot anterior al script mostraba Kodi `channelid` Alpha 3/Beta 2. También necesita verificarse que la consulta va a Kodi G3-AB y no otra instancia en el puerto 8080.

`G3AD_TVH_ALPHA_UUID_CHANGED=YES`
`G3AD_TVH_BETA_UUID_CHANGED=YES`
`G3AD_TVH_CURRENT_UUID_STABLE_2_SAMPLES=YES`
`G3AD_KODI_CHANNELS_2_SAMPLES=0_REPORTED_BUT_ERROR_NOT_CHECKED`
`G3AD_KODI_CHANNELS_DISAPPEARED=UNPROVEN`
`G3AD_RENAME_TRIAL=BLOCKED`
`G3AD_PVR_RESTART=NOT_AUTHORIZED_FOR_DIAGNOSIS`

Siguiente diagnóstico estrictamente GET/JSON-RPC: inspección de `error.code`, `error.message`, claves `result`, `channels` tipo/longitud y estado `PVR.GetProperties`; cuidado con `PVR.GetProperties` método/propiedades soportadas según versión, por lo que usar primero consulta de canales con control de errores. No publicar tokens, URLs de streaming ni contenido completo del log.


## G3-AD: JSON-RPC verificado devuelve 2 canales, corrige incertidumbre de muestras vacías

El operador ejecutó diagnóstico que comprueba explícitamente `error`, presencia de `result` y tipo de `channels`:

```text
JSONRPC_ERROR: None
RESULT_PRESENT: True
RESULT_KEYS: ['channels', 'limits']
CHANNELS_TYPE: list
TOTAL: 2
ID: 3 NOMBRE: G3AB Alpha
ID: 2 NOMBRE: G3AB Beta
```

**Conclusión limitada:** en esta nueva consulta, la petición JSON-RPC es correcta y Kodi tiene 2 canales (Alpha `channelid=3`, Beta `channelid=2`). Las dos respuestas previas con `TOTAL_KODI: 0` **no prueban borrado permanente**; el script previo carecía de `error` y validación del tipo de respuesta, pero **no sabemos** si fueron resultados temporalmente vacíos o errores JSON-RPC, porque las respuestas originales no se guardaron. No atribuir con certeza esos ceros a una excepción, error ni sincronización. TVH presentó ambos UUID distintos de baseline en los dos snapshots anteriores; motivo aún no demostrado. Aunque Kodi retorna 2 canales, **los IDs Kodi 3/2 no coinciden con el baseline 2/1**, por lo que aún falla conservación de identidad y sigue bloqueado un nuevo ensayo de renombrado hasta nueva verificación de estabilidad.

`G3AD_KODI_JSONRPC_VALID_LATEST=YES`; `G3AD_KODI_CHANNELS_LATEST=2`; `G3AD_KODI_ALPHA_ID_LATEST=3`; `G3AD_KODI_BETA_ID_LATEST=2`; `G3AD_KODI_ZERO_SAMPLES_CAUSE=UNKNOWN`; `G3AD_TVH_UUID_RECREATION_CAUSE=UNKNOWN`; `G3AD_RENAME_GATE=HOLD`. Evitar afirmar que se borraron canales, y no manipular SQL.


## G3-AD: contenedores sin reinicios; prepare.py sí reemplaza M3U completa (2026-11-21)

El operador verificó los contenedores de G3-AB:

```text
masqelec-pvr-g3ab-streams-1 nginx:alpine Up 7 hours
masqelec-pvr-g3ab-tvh-1 lscr.io/linuxserver/tvheadend:latest Up 7 hours
CONTENEDOR=/masqelec-pvr-g3ab-streams-1 ESTADO=running INICIO=2026-11-21T10:41:32.175032685Z REINICIOS=0
CONTENEDOR=/masqelec-pvr-g3ab-tvh-1 ESTADO=running INICIO=2026-11-21T10:41:32.176145808Z REINICIOS=0
```

Revisión directa de código en GitHub `develop`:
- `lab/pvr_g3ab/prepare.py`: `run(stage)` llama incondicionalmente `atomic_write(RUNTIME/playlist/playlist.m3u, playlist(stage))`; `atomic_write()` crea fichero temporal, escribe/fsync, y luego `os.replace(tmp,path)`. Es decir, **sustituye todo el fichero en cada etapa**, no parchea un EXTINF individual.
- `lab/pvr_g3ab/compose.yaml`: TVH monta `./runtime/playlist:/lab_playlist:ro` como directorio y usa persistencia `./runtime/tvh_config:/config`, Nginx monta streams en readonly; `restart: no` para ambos. No hay indicio de reinicio docker en los datos actuales.

**Conclusión sustentada**: regeneraciones UUID de Alpha/Beta ocurrieron dentro de una sesión de contenedor sin reinicio observado, y la restauración de playlist fue una sustitución atómica completa del fichero. **Hipótesis NO probada**: TVH reimportó de forma destructiva la M3U y recreó IDs debido al reemplazo atómico, a reescaneo periódico o a la configuración IPTV. Tampoco se descarta reinicio interno del proceso TVH (RestartCount Docker no equivale al contador de procesos) ni automatismos de TVH. Importante no afirmar que solo el `os.replace` causó el churn de Beta sin capturar tiempos, logs internos y configuración de la red IPTV.

`G3AD_DOCKER_TVH_RESTART_COUNT=0`; `G3AD_DOCKER_STREAMS_RESTART_COUNT=0`; `G3AD_PREPARE_REWRITES_WHOLE_PLAYLIST=YES`; `G3AD_UUID_CHURN_CAUSE=NOT_PROVEN`; `G3AD_NEXT_GATE=TVH_IPTV_IMPORT_FORENSICS_READ_ONLY`. Siguiente evidencia read-only: inspeccionar en API la configuración de la red IPTV (scan/create channels/muxes/refetch/reimport), comparar inventario UUID desde dos instantes sin más escrituras y revisar únicamente contadores/tipos de eventos del contenedor. No volcar configuración con credenciales ni logs completos en chat/GitHub. Mantener `G3AD_RENAME_GATE=HOLD`, no cambiar prepare ni producción hasta clasificar causa.


## Corrección causal G3-AD: operador intervino manualmente sobre bouquet (2026-11-21)

El operador aclaró: **«lo he reinicido yo el bouquet si es eso el problema»**. Es decir, durante la secuencia de ensayos existió una operación **manual de reinicio/refresco/reconstrucción de bouquet TVH** (acción exacta de interfaz y momento concreto aún por precisar). Este dato invalida utilizar el cambio simultáneo de UUID de Alpha y Beta como prueba de que `prepare.py restored`, `os.replace`, o el refresco periódico M3U **por sí solos** regeneraron ambos canales: hay un factor de confusión conocido. Sigue demostrado que el contenedor TVH no se reinició a nivel Docker, pero eso no excluye las operaciones de bouquet. No declarar causalidad de bouquet sin medir antes/después ni confundir actualizar bouquet con borrarlo/recrearlo.

`G3AD_OPERATOR_MANUAL_BOUQUET_ACTION=REPORTED`
`G3AD_BOTH_UUID_CHURN_ATTRIBUTABLE_TO_M3U=NO_EVIDENCE`
`G3AD_BOTH_UUID_CHURN_ATTRIBUTABLE_TO_BOUQUET=PLAUSIBLE_NOT_PROVEN`
`G3AD_DOCKER_RESTARTS=0`
`G3AD_HOT_RENAME_GATE=HOLD_UNTIL_STABLE_BASELINE`

En un futuro ensayo de refresco caliente, **prohibir operaciones manuales de bouquet, borrado/importación de canales y reinicio PVR entre snapshots**. Primero registrar UUID TVH, ID Kodi y estado de bouquet; luego cambiar exactamente el nombre de un canal, medir actualizaciones del lado TVH y Kodi y después restaurar, con pruebas aisladas. Si el operador aclara la operación exacta (p. ej., pulsar «Refresh» frente a eliminar/recrear), documentar diferencia explícita sin inventar.


## G3-AD: precisión del operador sobre bouquet y red IPTV (2026-11-21)

El operador aclaró que en TVH **deshabilitó y volvió a habilitar el bouquet** existente (NO dijo haberlo eliminado ni recreado). La operación se realizó manualmente durante el desarrollo de G3-AD; su instante exacto respecto a los snapshots y su efecto sobre UUID no fueron medidos directamente. Esto es factor de confusión específico para la regeneración simultánea de Alpha/Beta. No atribuir los UUID nuevos ni al reemplazo de M3U por `prepare.py`, ni exclusivamente a la alternancia del bouquet sin un ensayo de comparación.

Lectura del inventario de red `GET /api/mpegts/network/grid?start=0&limit=100` comunicada por operador:

```text
=== RED ===
UUID: 4a86445d515cfeb6dda45f45e2ee561d
NETWORKNAME: IPTV LOCAL
ENABLED: True
SKIPINITSCAN: True
AUTODISCOVERY: 0
REFETCH_PERIOD: 1
CHANNEL_NUMBER: 0
CAMPOS_CONFIG: ['channel_number', 'id
```

El último valor `CAMPOS_CONFIG` aparece **truncado** en el mensaje; no inferir claves restantes. `refetch_period=1` es valor observado de la configuración, no demuestra por sí solo cuándo se aplicó la última reimportación ni cuántos objetos reemplazó. `SKIPINITSCAN=True` y `AUTODISCOVERY=0` no prueban por sí solos política de estabilidad de identidad de canales.

`G3AD_BOUQUET_OPERATOR_ACTION=DISABLED_THEN_ENABLED`
`G3AD_BOUQUET_DELETED_RECREATED=NOT_REPORTED`
`G3AD_NETWORK_UUID=4a86445d515cfeb6dda45f45e2ee561d`
`G3AD_NETWORK_REFETCH_PERIOD=1`
`G3AD_UUID_CHURN_CAUSE=UNPROVEN_CONFOUNDED_BY_BOUQUET_TOGGLE`
`G3AD_FURTHER_BOUQUET_TOGGLE=HOLD`
`G3AD_NEXT_GATE=CONTROLLED_RENAME_HOT_REFRESH_ON_STABLE_INVENTORY`

Para ensayo controlado: no volver a alternar bouquet ni reiniciar PVR entre snapshots; verificar primero 2 canales TVH y Kodi, documentar ID/UUID actuales **sin exigir identidades antiguas 2/1**, después cambiar únicamente nombre sobre URL original y observar durante más de un período de `refetch` estable. No usar `PVR.GetChannels` como evidencia de `channelUpdate` emitido: hace falta instrumentación del cliente o captura HTSP aparte.


## G3-AD: tres observaciones convergidas y reparación del gate de identidad fijo

El operador ejecutó `tools/pvr_g3ac_observe.py --samples 3 --interval 10` tras la alternancia manual del bouquet. En **cada una de las tres muestras**:

```text
STATUS="OBSERVED_ONLY"
TVH_COUNT=2
KODI_COUNT=2
NAMES_MATCH=true
ID_PRESERVED=false
TVH_NAMES=["G3AB Alpha", "G3AB Beta"]
KODI_NAMES=["G3AB Alpha", "G3AB Beta"]
HTSP_EVENT_SEEN="NOT_MEASURED"
KODI_TRIGGER_SEEN="NOT_MEASURED"
CUID_MAPPING_PROVEN=false
SQLITE_TOUCHED=false
```

`ID_PRESERVED=false` aquí **no medía estabilidad entre muestras**: era una comparación incorrectamente anclada a Kodi Alpha=2/Beta=1 en código anterior. El último inventario JSON-RPC medido fue Alpha=3/Beta=2; los nombres TVH/Kodi sí coinciden en los tres snapshots, pero el observador antiguo **no imprimía los IDs ni UUID en cada lectura**, por lo que su constancia durante esos 30 s **no quedó demostrada**.

**Corrección en rama develop**: `tools/pvr_g3ac_observe.py` ahora captura mapeos por nombre `tvh_uuids_by_name` y `kodi_ids_by_name`, sin IDs fijos; el primer muestreo establece baseline por ejecución, los siguientes generan `TVH_UUIDS_STABLE_SINCE_SAMPLE1` y `KODI_IDS_STABLE_SINCE_SAMPLE1`; devuelve código 2 si cambian. Verifica dos nombres únicos de prefijo sintético G3AB, dos UUID TVH únicos y dos channelid Kodi enteros únicos; rechaza errores JSON-RPC, inventario erróneo y fuente inesperada. El observador **no** captura HTSP ni decide si `CUID` mapea TVH. El estado `STATUS=OBSERVED_ONLY` es lectura, nunca éxito del refresco en caliente. `tests/test_pvr_g3ac_observe.py` se amplió de 9 a **17 pruebas sintéticas**, **pendientes de ejecución Ubuntu**.

**Limitación a considerar**: comparar mapeos por nombre hace que un renombrado real cambie la clave del mapa y dé `STABLE=false` aunque el UUID canal se conserve; este observador es un **gate de estabilidad en ventana sin cambios**, no la herramienta definitiva para seguir identidad durante un renombrado. Para ese ensayo se requerirá un tracker por identificador y transición explícita de nombre de Alpha (G3AB Alpha → G3AB Alpha Renamed) con baseline previo, no reinterpretar `STABLE=false` de un renombrado como recreación de UUID.

`G3AD_G3AC_OBSERVER_STATIC_NAMES_MATCH=PASS_3`
`G3AD_G3AC_OLD_ID_PRESERVED_FLAG=INVALID_HARDCODED_BASELINE`
`G3AD_G3AC_DYNAMIC_OBSERVER_IMPLEMENTED=YES`
`G3AD_G3AC_DYNAMIC_UNIT_TESTS=PENDING_17`
`G3AD_G3AC_DYNAMIC_OBSERVER_LAB=PENDING`
`G3AD_HOT_RENAME_EVENT_PROVEN=NO`

Comandos:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ac_observe.py' -v
python3 service.cloud.masqelec/tools/pvr_g3ac_observe.py --samples 3 --interval 10
```

Sin reinicio PVR, sin bouquet toggle, sin cambio M3U, sin escrituras SQLite.


## G3-AD: gate de estabilidad dinámica superado en Ubuntu (operador 2026-11-21)

El operador comunicó ejecución real de los nuevos tests y del observador actualizado:

```text
Ran 17 tests in 0.003s
OK
G3AC_SAMPLE=1: TVH_COUNT=2 KODI_COUNT=2 NAMES_MATCH=true
 TVH_UUIDS_BY_NAME={"G3AB Alpha":"dba29285ca808eb6486d364f994b05db","G3AB Beta":"3bf90ae8eb828a6e4961902724a1f380"}
 KODI_IDS_BY_NAME={"G3AB Alpha":3,"G3AB Beta":2}
 TVH_UUIDS_STABLE_SINCE_SAMPLE1=null
 KODI_IDS_STABLE_SINCE_SAMPLE1=null
G3AC_SAMPLE=2: NAMES_MATCH=true TVH_UUIDS_STABLE_SINCE_SAMPLE1=true KODI_IDS_STABLE_SINCE_SAMPLE1=true
G3AC_SAMPLE=3: NAMES_MATCH=true TVH_UUIDS_STABLE_SINCE_SAMPLE1=true KODI_IDS_STABLE_SINCE_SAMPLE1=true
HTSP_EVENT_SEEN="NOT_MEASURED"
KODI_TRIGGER_SEEN="NOT_MEASURED"
CUID_MAPPING_PROVEN=false
SQLITE_TOUCHED=false
```

`G3AD_DYNAMIC_OBSERVER_UNIT=PASS_17_OF_17`
`G3AD_DYNAMIC_OBSERVER_LAB=PASS_3_SNAPSHOTS`
`G3AD_TVH_ALPHA_UUID_BASELINE=dba29285ca808eb6486d364f994b05db`
`G3AD_TVH_BETA_UUID_BASELINE=3bf90ae8eb828a6e4961902724a1f380`
`G3AD_KODI_ALPHA_ID_BASELINE=3`
`G3AD_KODI_BETA_ID_BASELINE=2`
`G3AD_NAMES_MATCH=YES`
`G3AD_HOT_REFRESH_RENAME=NOT_YET_RUN`

Los valores null de la primera muestra son correctos: todavía no existe muestra precedente. Dos muestras posteriores confirman estabilidad bajo inventario sin cambios en un lapso de 20 segundos. Esto **no** demuestra que actualice etiquetas en caliente ni que se haya medido evento HTSP, CUID o callback. A continuación hacer seguimiento de **identidad por UUID TVH e ID Kodi**, no clave por nombre, en un renombrado de Alpha de una sola dimensión (URL original restaurada, bouquet intacto, PVR sin reiniciar).


## G3-AD: instrumentación controlada de renombrado preparada (sin ejecutar en Ubuntu)

Nuevo `tools/pvr_g3ad_rename_watch.py` y `tests/test_pvr_g3ad_rename_watch.py` (**17 tests creados, todavía pendientes de ejecución**). Se basa en el observador G3-AC, pero para un renombrado sigue específicamente el canal Alpha por identificador TVH/Kodi mientras cambia el texto, y compara el canal Beta para protegerlo. Rechaza canal inesperado, duplicado, sin UUID/ID único, inventario distinto de dos canales, o renombrado ya aplicado antes del baseline. Detecta `G3AD=IDENTITY_CHANGED_ABORT` si cambia UUID/ID en la ventana. Si TVH renombra y Kodi no lo hace antes de finalizar, devuelve código 4 `G3AD=TVH_RENAMED_KODI_NOT_OBSERVED`; si ambos se actualizan devuelve código 0 `G3AD=BOTH_RENAMES_OBSERVED_NO_HTSP_TRACE`; sin renombrado TVH, código 3. **El watcher no captura eventos HTSP ni callback Kodi**, por lo que un resultado favorable solo demuestra convergencia de etiquetas dentro de la ventana, no mecanismos causales. Solo lectura, fuentes G3-AB de loopback, no escribe M3U, ni SQL, ni altera Kodi/PVR, ni reinicia servicios. No usar en el master.

**Gate de operador antes de ensayo**:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ad_rename_watch.py' -v
```

Después de confirmar tests, comprobar que M3U vuelve a URL original `ch1.ts` y que Alpha tiene nombre sin `Renamed`; verificar estado actual de TVH/Kodi y mantener conexión pvr.hts. Con **dos terminales**, arrancar primero:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
python3 -u service.cloud.masqelec/tools/pvr_g3ad_rename_watch.py --samples 40 --interval 5
```

Tras ver `G3AD_SAMPLE=1` y baseline validado, en **segunda terminal exclusivamente en G3-AB**, ejecutar:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab
python3 prepare.py rename
```

No reiniciar ni alternar el bouquet ni PVR durante la captura. La reimportación de TVH configurada a refetch_period=1 puede tardar más de un minuto, por eso se deja una ventana de 200 s (40 muestras x 5 s). El watcher registra estados sanitizados y aborta ante modificaciones de ID. Conservar logs solo si se filtran secretos. **No ejecutar todavía el paso de renombrado hasta pasar tests de operador y obtener baseline en primera muestra.** Después, documentar las medidas y decidir instrumentación HTSP.

`G3AD_RENAME_WATCHER_CODE=COMMITTED`
`G3AD_RENAME_WATCHER_UNIT=NOT_YET_RUN_BY_OPERATOR`
`G3AD_HOT_RENAME_RESULT=PENDING`
`G3AD_MASTER_UNTOUCHED=YES`


## G3-AD: etapa RENAME generada por operador, propagación aún pendiente (2026-11-21)

El operador comunicó la salida del generador `lab/pvr_g3ab/prepare.py rename`:

```text
G3AB_STAGE=RENAME
G3AB_CUID_COUNT=2
G3AB_MASTER_UNTOUCHED=YES
G3AB_G3W_UNTOUCHED=YES
```

Esta evidencia acredita solamente que el generador sintético realizó la escritura de la M3U de laboratorio de etapa `rename`; **no** prueba que Tvheadend haya importado el cambio ni que `pvr.hts`/Kodi hayan actualizado el canal. No consta todavía el resultado de las 17 pruebas unitarias del nuevo observador `test_pvr_g3ad_rename_watch.py` ni la salida de la **terminal 1** de `pvr_g3ad_rename_watch.py`; no afirmar que el ensayo observacional haya sido iniciado o completado.

`G3AD_RENAME_PLAYLIST_WRITE=REPORTED_SUCCESS`
`G3AD_RENAME_WATCHER_UNIT=UNREPORTED`
`G3AD_RENAME_WATCHER_OUTPUT=PENDING`
`G3AD_TVH_RENAME_PROPAGATED=UNPROVEN`
`G3AD_KODI_HOT_RENAME_PROPAGATED=UNPROVEN`

**No reiniciar PVR/bouquet ni restaurar M3U** mientras se intenta recopilar el resultado de la observación de la terminal 1; pedir salida desde `G3AD_SAMPLE=1` hasta último estado/código de salida. Si watcher no se inició antes de `prepare.py rename`, declararlo y repetir en otra ocasión desde baseline restaurado, sin fingir medición antes/durante.


## G3-AD: reproducción controlada de divergencia de nombre con identidades estables (2026-11-21)

Tras aplicar `python3 prepare.py rename`, el operador aportó salida **parcial** del watcher G3-AD:

```text
G3AD_SAMPLE=1
TVH_ALPHA_NAME="G3AB Alpha"
TVH_ALPHA_UUID="dba29285ca808eb6486d364f994b05db"
TVH_BETA_UUID="3bf90ae8eb828a6e4961902724a1f380"
KODI_ALPHA_NAME="G3AB Alpha"
KODI_ALPHA_ID=3
KODI_BETA_ID=2
TVH_ALPHA_RENAMED=false
KODI_ALPHA_RENAMED=false
NAMES_MATCH=true
TVH_UUID_STABLE=null
KODI_ID_STABLE=null
G3AD_SAMPLE=2
TVH_ALPHA_NAME="G3AB Alpha"
TVH_ALPHA_UUID="dba29285ca808eb6486d364f994b05db"
TVH_BETA_UUID="3bf90ae8eb828a6e4961902724a1f380"
KODI_ALPHA_NAME="G3AB Alpha"
KODI_ALPHA_ID=3
KODI_BETA_ID=2
TVH_ALPHA_RENAMED=false
KODI_ALPHA_RENAMED=false
NAMES_MATCH=true
TVH_UUID_STABLE=true
KODI_ID_STABLE=true
G3AD_SAMPLE=16
TVH_ALPHA_NAME="G3AB Alpha Renamed"
TVH_ALPHA_UUID="dba29285ca808eb6486d364f994b05db"
TVH_BETA_UUID="3bf90ae8eb828a6e4961902724a1f380"
KODI_ALPHA_NAME="G3AB Alpha"
KODI_ALPHA_ID=3
KODI_BETA_ID=2
TVH_ALPHA_RENAMED=true
KODI_ALPHA_RENAMED=false
NAMES_MATCH=false
TVH_UUID_STABLE=true
KODI_ID_STABLE=true
```

**Confirmado:** TVH importó rename exclusivamente y conservó UUID de Alpha/Beta, mientras Kodi mantenía `channelid` 3/2 y el nombre anterior al menos hasta el sample 16 (intervalo configurado 5 segundos, ~75 segundos desde primera muestra). La divergencia no se debe a pérdida de identidad durante el renombrado. El watcher, que solo consulta GET/JSONRPC, no tiene telemetría de eventos HTSP ni callback nativo. **No consta todavía salida final del watcher (sample 40/resultado/código)**: NO declarar fallo persistente durante todos los 200 segundos, ni asignar causa a TVH/pvr.hts/Kodi.

`G3AD_TVH_ALPHA_RENAME_APPLIED=YES`
`G3AD_TVH_CHANNEL_UUIDS_DURING_RENAME=STABLE`
`G3AD_KODI_JSONRPC_IDS_DURING_RENAME=STABLE`
`G3AD_KODI_LABEL_STALE_AT_SAMPLE16=YES`
`G3AD_HTSP_EVENT_EMITTED=NOT_MEASURED`
`G3AD_PVR_HTS_TRIGGER_CALLED=NOT_MEASURED`
`G3AD_WATCHER_FINAL_STATUS=PENDING`

No reiniciar Kodi/PVR, no alternar bouquet ni restaurar playlist hasta capturar salida final. Después investigar logs nativos sin publicar secretos. No usar este resultado como prueba de que no llega el evento HTSP.


## G3-AD: resultado final de renombrado en caliente — Kodi NO converge (operador, 2026-11-21)

Después de observar el renombrado de Alpha en TVH en la muestra 16 manteniendo UUID TVH de Alpha/Beta y channelid Kodi 3/2, el operador confirmó que el proceso finalizó por sí mismo con:

```text
G3AD=TVH_RENAMED_KODI_NOT_OBSERVED
```

El observador `pvr_g3ad_rename_watch.py` devuelve este marcador al agotar su ventana configurada (`--samples 40 --interval 5`), cuando ha visto `tvh_alpha_renamed=true` en alguna muestra y **nunca** ha observado `kodi_alpha_renamed=true`. Equivale a unos 195 segundos entre la primera y última muestra (40 muestras espaciadas por 5 segundos), más tiempo de consultas. No se ha compartido la salida textual exacta de la muestra 40 ni el código de salida, pero el marcador final del propio proceso sí se ha comunicado.

`G3AD_RENAME_TVH_ACCEPTED=YES`
`G3AD_RENAME_KODI_HOT_CONVERGENCE=NO_IN_OBSERVATION_WINDOW`
`G3AD_RENAME_40_SAMPLES=REPORTED_FINAL_MARKER`
`G3AD_TVH_UUIDS_STABLE_AT_SAMPLE16=YES`
`G3AD_KODI_IDS_STABLE_AT_SAMPLE16=YES`
`G3AD_RENAME_WATCHER_EXIT_CODE=NOT_REPORTED`
`G3AD_HTSP_CHANNELUPDATE_EMITTED=NOT_MEASURED`
`G3AD_PVR_NATIVE_TRIGGER_CALLED=NOT_MEASURED`
`G3AD_HOT_REFRESH_ROOT_CAUSE=UNPROVEN`

**Diagnóstico concluyente en alcance estricto:** la actualización de nombre se refleja en TVH pero no en el nombre de Kodi dentro del intervalo observado **sin reinicio PVR reportado**. Con el código inspeccionado de pvr.hts Omega, hay un recorrido `channelUpdate → ParseChannelAddOrUpdate → TriggerChannelUpdate`; falta saber si el mensaje es emitido, recibido y si produce trigger. No saltar a soluciones destructivas (borrar SQLite, recrear canales, alternar bouquet, reiniciar PVR automáticamente). Conservar temporalmente el estado Alpha Renamed en TVH frente a Alpha en Kodi para una inspección del log y, si es necesario, una medición HTSP pasiva; no imprimir tokens, secretos ni URL del master.


## G3-AE: Kodi log después de la divergencia de rename (operador, 2026-11-21)

Captura read-only realizada con TVH `G3AB Alpha Renamed` y Kodi `G3AB Alpha` después del marcador `G3AD=TVH_RENAMED_KODI_NOT_OBSERVED`:

```text
LOG_LINES: 629
PVR_HTS_COUNT: 84
HTSP_MESSAGES_COUNT: 0
CHANNEL_TRIGGER_COUNT: 0
CHANNEL_RENAMED_COUNT: 0
CHANNEL_ORIGINAL_COUNT: 0
PVR_ERRORS_COUNT: 4
LOG_LAST_MODIFIED: 1795284638.4809587
```

El script cuenta coincidencias de expresiones regulares, **no** comprueba si las 4 líneas son incidentes durante la ventana G3-AD ni si el log tiene suficiente granularidad para instrumentar HTSP. El conteo de cero no demuestra que el servidor dejara de emitir `channelUpdate`, ni que el cliente dejara de procesarlo. No se ha revisado todavía el texto de esas 4 líneas, que puede contener URLs/credenciales. El fichero sí existe. `G3AE_KODI_LOG_LINES=629`; `G3AE_CHANNELUPDATE_LITERAL_COUNT=0`; `G3AE_PVR_ERRORS_REGEX_MATCHES=4_UNCLASSIFIED`; `G3AE_HTSP_EVENT_DELIVERY=NOT_MEASURED`; `G3AE_ROOT_CAUSE=UNKNOWN`.

**Siguiente acción de mínimo riesgo**: diagnóstico de líneas de error con sanitización local de direcciones, credenciales y tokens, devolviendo tipo/nivel/posición temporal y mensaje redactado. Verificar si los incidentes son históricos y, si la telemetría es insuficiente, diseñar observación HTSP de laboratorio separada, sin tocar `pvr.hts` en master ni reiniciar bouquet/PVR. Evitar publicación de logs brutos.


## G3-AE: cuatro líneas FAILED clasificadas por hora (operador, 2026-11-21)

El operador realizó el diagnóstico local del `kodi.log` (sin mostrar los mensajes):

```text
LOG_MODIFICADO: 2026-11-21T19:10:38.480959
LINEA: 224
FECHA_LOG: 2026-11-21 12:07:56
CATEGORIAS: FAILED
---
LINEA: 296
FECHA_LOG: 2026-11-21 12:09:57
CATEGORIAS: FAILED
---
LINEA: 363
FECHA_LOG: 2026-11-21 18:27:59
CATEGORIAS: FAILED
---
LINEA: 446
FECHA_LOG: 2026-11-21 18:29:20
CATEGORIAS: FAILED
```

Estas cuatro líneas satisfacen la regex `(pvr|htsp).*(error|failed|disconnect|reconnect)` y contienen `failed`; **no** tenemos el mensaje ni la causa, ni sabemos si se refieren a `channelUpdate`, reconexión, HTTP o reproducción. Es posible que algunas correspondan a ensayos anteriores. La marca de modificación del log a las 19:10:38 no data por sí sola el instante del fallo de refresco. En particular no concluir causalidad por cercanía temporal hasta confrontar la cronología del renombrado. `G3AE_PVR_FAILED_LINES=4`, `G3AE_FAILED_ACTIONS=UNKNOWN`, `G3AE_HTSP_EMISSION_CAPTURE=NOT_DONE`, `G3AE_ROOT_CAUSE=UNKNOWN`.

Próximo diagnóstico: obtener solamente los tipos y palabras clave de error con sanitización o inspección local de líneas 224,296,363,446 sin publicar URLs, tokens, contraseñas, IPs o datos de producción. Mantener el estado TVH Alpha Renamed / Kodi Alpha, sin reinicios ni alternancia bouquet; si los mensajes no corresponden a eventos, pasar a instrumentación HTSP aislada.
