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
