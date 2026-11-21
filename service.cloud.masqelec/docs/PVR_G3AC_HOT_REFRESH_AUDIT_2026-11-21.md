# G3-AC — auditoría de refresco en caliente TVH → HTSP → pvr.hts → Kodi (2026-11-21)

## Evidencia experimental anterior

En G3-AB, los cambios de nombre y posterior restauración se reflejaron en Tvheadend pero **no** en el `label` de Kodi durante una conexión PVR existente. Una reconexión/reinicio del sistema PVR realizada por operador actualizó la etiqueta conservando `channelid` (Alpha 2, Beta 1), sin tocar SQLite. El cambio de URL recreó UUID de canal, servicio y mux de Alpha en TVH; después de refrescar PVR, Kodi mantuvo `channelid=2`. TVH confirmó suscripción `Running` con bytes positivos y cero errores; reproducción audiovisual no confirmada explícitamente. El atributo `CUID` en playlist **no** protegió los UUID de TVH.

## Auditoría de código fuente: rama Omega

Fuente inspeccionada directamente por GitHub: https://github.com/kodi-pvr/pvr.hts/blob/Omega/src/Tvheadend.cpp (rama de desarrollo Omega; **no** se ha cotejado el SHA exacto de la compilación CoreELEC `pvr.hts 21.2.6.1`).

- `AsyncProcess` (aprox. líneas 1738–1744) reconoce mensajes `channelAdd`, `channelUpdate`, `channelDelete` y deriva `channelUpdate` a `ParseChannelAddOrUpdate(msg, false)`.
- `ParseChannelAddOrUpdate` (aprox. líneas 2129–2220) busca `channelId`, lee opcionalmente `channelName`, actualiza `Channel` en caché y, **solo si `channel != comparison`**, marca `TriggerChannelUpdate()` cuando el estado asíncrono supera `ASYNC_CHN`.
- La cola `m_events` contiene `HTSP_EVENT_CHN_UPDATE`. Al procesar la cola **fuera del mutex** (aprox. líneas 1820–1858), llama a `kodi::addon::CInstancePVRClient::TriggerChannelUpdate()`.
- `GetChannels` (aprox. líneas 336–372) entrega `SetUniqueId(channel.GetId())` y `SetChannelName(channel.GetName())` a Kodi. El identificador del plugin está basado en el **ID HTSP TVH**, no en el atributo de playlist CUID.
- El servidor Tvheadend dispone de `htsp_channel_update()` para notificar `channelUpdate`, y de un evento de igual nombre para EPG now/next que puede omitir `channelName`; no confundir ambas variantes. Fuente: https://github.com/tvheadend/tvheadend/blob/master/src/htsp_server.c.
- Kodi Dev Kit documenta `TriggerChannelUpdate()` y `TriggerChannelGroupsUpdate()` como **callbacks internos de addon nativo**, no acciones expuestas directamente a scripts Python: https://xbmc.github.io/docs.kodi.tv/master/kodi-dev-kit/group__cpp__kodi__addon__pvr___channels.html.

## Hipótesis abiertas

1. El TVH no emitió el `channelUpdate` con `channelName` mientras estaba conectado `pvr.hts`.
2. La notificación se emitió pero no llegó o el cliente no la procesó.
3. El cliente procesó el mensaje pero no detectó cambio relevante o no activó `TriggerChannelUpdate`.
4. La llamada al callback ocurrió, pero Kodi no actualizó la etiqueta observable.

**No se ha probado ninguna causa concreta.** La documentación del código fuente solo confirma que existen los mecanismos.

## Instrumento nuevo: solo lectura

`tools/pvr_g3ac_observe.py` consulta los endpoints de los laboratorios G3-AB `127.0.0.1:19991` (TVH) y `127.0.0.1:8080` (Kodi JSON-RPC) en intervalos acotados. Contrasta inventario y `name`/`label` y registra si siguen los IDs base de Kodi. **No captura ni decodifica HTSP, no prueba emisión de eventos ni mide si Kodi invocó el callback**. No reinicia servicios ni modifica M3U ni SQL. Bloquea inventarios inesperados, por seguridad.

`tests/test_pvr_g3ac_observe.py` incluye **9 tests sintéticos**, pendientes de ejecución del operador.

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/tools/pvr_g3ac_observe.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ac_observe.py' -v
python3 service.cloud.masqelec/tools/pvr_g3ac_observe.py --samples 3 --interval 10
```

Interpretación: `NAMES_MATCH=true` describe solo convergencia del snapshot y **no** demuestra que el mecanismo caliente funcionó; el observador no inicia cambios. Para reproducir y medir el fallo se requerirá un escenario controlado de cambio de nombre **después** de registrar el baseline actual y una forma de observar eventos de cliente (logging de depuración del addon Kodi Omega o herramienta HTSP dedicada). No reutilizar `prepare.py rename` a ciegas desde etapa URL, ya que cambiaría simultáneamente nombre y URL. Primero restaurar la URL base y verificar convergencia; planear escenarios sin alterar datos históricos.

## Gates

`G3AC_SOURCE_CODE_AUDIT=COMPLETE_OMEGA_BRANCH`
`G3AC_CORELEC_BINARY_PARITY=UNPROVEN`
`G3AC_OBSERVER_IMPLEMENTED=YES`
`G3AC_UNIT_TESTS=PENDING`
`G3AC_HOT_REFRESH_CAUSE=UNPROVEN`
`G3AC_PRODUCTION_CUTOVER=NO`
`G3AC_MASTER_TOUCHED=NO`


## Resultado real G3-AC del operador — 9/9 y tres observaciones coherentes

```text
Ran 9 tests in 0.000s
OK
G3AC_SAMPLE=1
STATUS="OBSERVED_ONLY"
TVH_COUNT=2
KODI_COUNT=2
NAMES_MATCH=true
ID_PRESERVED=true
TVH_NAMES=["G3AB Alpha", "G3AB Beta"]
KODI_NAMES=["G3AB Alpha", "G3AB Beta"]
HTSP_EVENT_SEEN="NOT_MEASURED"
KODI_TRIGGER_SEEN="NOT_MEASURED"
CUID_MAPPING_PROVEN=false
SQLITE_TOUCHED=false
G3AC_SAMPLE=2
STATUS="OBSERVED_ONLY"
TVH_COUNT=2
KODI_COUNT=2
NAMES_MATCH=true
ID_PRESERVED=true
TVH_NAMES=["G3AB Alpha", "G3AB Beta"]
KODI_NAMES=["G3AB Alpha", "G3AB Beta"]
HTSP_EVENT_SEEN="NOT_MEASURED"
KODI_TRIGGER_SEEN="NOT_MEASURED"
CUID_MAPPING_PROVEN=false
SQLITE_TOUCHED=false
G3AC_SAMPLE=3
STATUS="OBSERVED_ONLY"
TVH_COUNT=2
KODI_COUNT=2
NAMES_MATCH=true
ID_PRESERVED=true
TVH_NAMES=["G3AB Alpha", "G3AB Beta"]
KODI_NAMES=["G3AB Alpha", "G3AB Beta"]
HTSP_EVENT_SEEN="NOT_MEASURED"
KODI_TRIGGER_SEEN="NOT_MEASURED"
CUID_MAPPING_PROVEN=false
SQLITE_TOUCHED=false
```

`G3AC_UNIT_TESTS=PASS_9`; `G3AC_OBSERVER_LAB=PASS_3_OBSERVATIONS`; `G3AC_CURRENT_TVH_KODI_NAMES_MATCH=YES`; `G3AC_KODI_IDS_BASELINE_MATCH=YES`; `G3AC_HOT_REFRESH=NOT_TESTED_BY_STATIC_OBSERVATIONS`; `G3AC_HTSP_EVENT=NOT_MEASURED`; `G3AC_TRIGGER_CHANNEL_UPDATE=NOT_MEASURED`. **Importante:** el valor `SQLITE_TOUCHED=false` es una propiedad del script observador, no prueba que ningún otro proceso haya escrito en la base de datos. En estos tres snapshots no se introdujo ningún cambio entre muestras; por tanto **no prueban** actualización en caliente. La ejecución no comunicó fallos.

El siguiente ensayo debe preparar un cambio de nombre de una sola dimensión sobre el **estado real actual** de la M3U, observar simultáneamente TVH/Kodi y, en paralelo, el registro de eventos de `pvr.hts` si es técnicamente observable sin recompilar el cliente. No reiniciar PVR durante el segmento de observación en caliente. Mantener el master fuera de alcance.


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


## Próximo paso confirmado por documentación oficial: logging Kodi PVR de laboratorio

La documentación oficial Kodi https://kodi.wiki/view/Settings/System/Logging confirma **Settings → System → Logging → Enable debug logging** y **Enable component-specific logging → Specify component-specific logging**, con el componente **PVR component** (código 1048576). En el perfil G3-AB aislado, habilitar debug logging y componente PVR; puede añadirse Add-ons para investigar el cliente. La activación **no** garantiza que el código nativo emita cada mensaje HTSP (`channelUpdate` puede no aparecer). Antes de modificar M3U, comprobar nivel efectivo por extracto **filtrado y redactado** de registros, sin publicar credenciales/URLs; las líneas completas del log pueden ser sensibles.

El ensayo de solo-rename no debe empezar desde la M3U `url` actual (URL alternativa presente); primero restaurar la playlist base y esperar la convergencia. Mantener capturas de logs y observador `G3-AC` sincronizadas. No reiniciar PVR/Kodi en mitad de la observación del refresco en caliente. Cualquier reinicio para habilitar debug, si hace falta, se realiza **antes** de iniciar el experimento y solo en el perfil de laboratorio.


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


## G3-AE cierre de clasificación por hashes — resultado del operador (2026-11-21)

Se calcularon huellas SHA-256 de las líneas de Kodi 224, 296, 363, 446, después de eliminar con regex únicamente la marca de tiempo inicial estándar:

```text
LINEA: 224 HUELLA: 88f327c0364588f1
LINEA: 296 HUELLA: fbb57298b7e56950
LINEA: 363 HUELLA: a77b4ad3f9dc034a
LINEA: 446 HUELLA: e8613d1ccefd48ff
```

Las cuatro huellas **son distintas**. Por tanto, las líneas normalizadas no eran idénticas byte a byte; ello **no demuestra** que sean cuatro errores semánticamente diferentes (pueden variar IDs, subtimestamps, mensajes dinámicos o campos) ni una relación con el renombrado. No hay contenido suficiente para clasificarlas y la búsqueda textual `kodi.log` no mostró mensajes `channelUpdate` o `TriggerChannelUpdate`. **Cerrar investigación basada solo en hashes**, pasar a G3-AF: diseñar captura de eventos HTSP y comprobación del cliente en laboratorio, comenzar siempre la captura antes de un nuevo cambio controlado. El evento pasado NO puede observarse retroactivamente por una nueva captura.

`G3AE_ERROR_HASHES_DISTINCT=YES_4_OF_4`
`G3AE_ERRORS_RELATED_TO_RENAME=UNPROVEN`
`G3AE_LOG_HUNT=INCONCLUSIVE_STOP`
`G3AF_HTSP_PASSIVE_OBSERVER=NOT_YET_IMPLEMENTED`
`G3AD_RENAME_DIVERGENCE_REPRODUCED=YES`

Preservar el estado TVH `G3AB Alpha Renamed` / Kodi `G3AB Alpha` hasta preparar experimento instrumentado. No reiniciar PVR/bouquet ni tocar SQLite/master. Para generar nuevo evento HTSP, habrá que volver a baseline o realizar una transición de nombre controlada **después de iniciar la captura**; evitar deducir que una suscripción HTSP nueva tiene acceso a eventos históricos.
