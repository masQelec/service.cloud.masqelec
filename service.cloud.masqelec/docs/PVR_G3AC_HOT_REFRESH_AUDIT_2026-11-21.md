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
