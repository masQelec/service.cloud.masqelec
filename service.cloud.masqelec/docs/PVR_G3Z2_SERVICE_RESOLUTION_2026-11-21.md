# G3-Z2 — Resolución de servicios IPTV por UUID (2026-11-21)

## Hallazgo G3-Z

El operador informó `Ran 10 tests ... OK`, `G3Z=SHAPES_ONLY`, 2 canales, 2 referencias, 0 sin servicio, `REFERENCE_SHAPES={"str": 2}`; UUID y CUID entre capas aún **no probados**.

La documentación oficial Tvheadend explica que `channel/grid.services` contiene UUID de servicios y que `service/list?enum=1` devuelve un catálogo reducido de `key`/`val`. En este laboratorio debemos contrastar los datos reales, no limitarse a asumir que las cadenas observadas son UUID.

Referencias:
- https://docs.tvheadend.org/documentation/development/json-api/api-description/channel
- https://docs.tvheadend.org/documentation/development/json-api/api-description/service
- https://docs.tvheadend.org/documentation/development/object-class-relationships

## Cambios en develop

Nuevo script `tools/pvr_g3z2_service_resolution_lab.py`:
- Un único GET al inventario de canales TVH de G3-W `127.0.0.1:19981/api/channel/grid?start=0&limit=20000`.
- Un único GET al catálogo `127.0.0.1:19981/api/service/list?enum=1`.
- Compara la totalidad de las referencias de `services` contra los `key` del catálogo. Exige 32 caracteres hexadecimales para UUID, inventarios no vacíos, sin paginación incompleta, referencias de canal no vacías, sin duplicados por canal, UUID de canal únicos y IDs del catálogo únicos.
- Informa exclusivamente de conteos y del número de referencias sin resolver; no publica UUID, URL, nombres ni credenciales.
- Ante datos inválidos devuelve `G3Z2=BLOCKED`, nunca habilita borrado.
- No accede a Kodi ni SQLite; no crea o elimina muxes/servicios ni actúa sobre el master.

Pruebas offline en `tests/test_pvr_g3z2_service_resolution_lab.py`: 13 casos, incluidos servicios compartidos (que **no** deben considerarse relación unívoca), IDs inválidos o duplicados, respuestas truncadas y ausencia de autorización para borrar. Ejecución real pendiente.

### Validación en Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/tools/pvr_g3z2_service_resolution_lab.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3z2_service_resolution_lab.py' -v
python3 service.cloud.masqelec/tools/pvr_g3z2_service_resolution_lab.py
```

Basta TVH lab en 19981; Kodi puede estar cerrado. No ejecutar en CoreELEC.

Si devuelve `TVH_SERVICE_UUID_RELATION_PASS` habrá quedado demostrada **solo** la relación canal→servicio en TVH del laboratorio. `CUID_MAPPING_PROVEN=NO` y `TVH_TO_KODI_IDENTITY_PROVEN=NO` permanecerán bloqueados. La relación exacta con la playlist y el backend Kodi exige pruebas adicionales con fixture CUID y/o metadatos HTSP.

**Producción no alterada. Cambio de algoritmo legacy no autorizado.**


## Resultado real operador — G3-Z2 PASS, 2026-11-21

```text
Ran 13 tests in 0.001s
OK
G3Z2=TVH_SERVICE_UUID_RELATION_PASS
CHANNEL_COUNT=2
AVAILABLE_SERVICE_COUNT=3
SERVICE_REFERENCE_COUNT=2
UNIQUE_REFERENCED_SERVICES=2
UNRESOLVED_REFERENCES=0
TVH_CHANNEL_SERVICE_REFERENCE_PROVEN=YES
CUID_MAPPING_PROVEN=NO
TVH_TO_KODI_IDENTITY_PROVEN=NO
DELETION_AUTHORIZED=NO
PRODUCTION_TOUCHED=NO
```

`G3Z2_UNIT=PASS_13` y `G3Z2_LAB_TVH_SERVICE_UUID_RELATION=PASS`. Las dos referencias se resuelven en catálogo service/list de TVH. Este gate **no** acredita una vinculación CUID→servicio, ni TVH UUID→Kodi ID, ni eliminación segura.

**Observación adicional importante:** 3 servicios descubiertos, 2 referenciados por los 2 canales, sin referencias pendientes. Puede tratarse de un servicio residual del paso 2→3→2, pero **no está demostrado**: contar disponibles menos referenciados no identifica por sí solo un huérfano que debiera eliminarse. Siguiente gate: estudiar por API GET la relación de servicios no vinculados con muxes y con el conjunto IPTV sintético, sin borrar ni alterar configuración, y distinguir limpieza de canales frente a retención legítima de servicios/muxes.


## Verificación posterior: servicio no vinculado, origen desconocido

El operador consultó `channel/grid` y `service/list?enum=1` mediante GET y obtuvo:

```text
CANALES: 2
SERVICIOS: 3
SERVICIOS_SIN_CANAL: 1
SERVICIO_3_SIN_CANAL: False
```

**Interpretación acotada:** hay una entrada de `service/list` sin referencia de canal, pero el texto de su `val` no contiene literalmente `G3W Synthetic 3`. `False` no identifica la procedencia del servicio, ni prueba que no sea residual del ensayo. Tampoco autoriza eliminarlo; un servicio no asociado a un canal puede seguir perteneciendo a un mux de TVH. Siguiente gate: inspección de metadatos de `service/grid` y relación con muxes en lectura, con privacidad (no imprimir URLs, UUID ni credenciales); no realizar `idnode/delete`.


## Corrección del endpoint de diagnóstico (2026-11-21)

El operador ejecutó la consulta diagnóstica posterior y obtuvo `SERVICE_GRID_ERROR: HTTPError` al solicitar `/api/service/grid`. La documentación oficial de Tvheadend **no enumera** `service/grid` como API del inventario MPEGts; la ruta documentada es **`/api/mpegts/service/grid`**. Los muxes se consultan mediante `/api/mpegts/mux/grid`. Fuentes: https://docs.tvheadend.org/documentation/development/json-api/api-description/mpegts y https://docs.tvheadend.org/documentation/development/json-api/api-description/service.

`HTTPError` es genérico: no consta si fue 404, 401, 403, 400 u otro código. No inferir corrupción de TVH ni afirmar el código hasta verlo. Corregir la consulta de metadatos de servicio y mantener exclusivamente GET. La posible presencia de un servicio no vinculado a un canal no justifica eliminarlo. `PRODUCTION_TOUCHED=NO`.


## G3-Z3: servicio sin canal encontrado en inventario MPEG-TS

Operador ejecutó GET `mpegts/service/grid?start=0&limit=20000&hidemode=none` y contrastó con `channel/grid` y `service/list?enum=1`. Resultado:

```text
SERVICE_GRID_TOTAL: 3
SERVICIOS_SIN_CANAL: 1
SERVICIOS_SIN_CANAL_EN_GRID: 1
```

Campos observados para esa entrada: `uuid`, `network`, `multiplex`, `multiplex_uuid`, `sid`, `srcid`, `svcname`, `created`, `last_seen`, `enabled`, `channel` (list), `auto`, entre otros.

Conclusión estricta: el servicio sin referencias desde canales existe efectivamente en `mpegts/service/grid`, pero **no está acreditado que proceda del canal G3W Synthetic 3**, ni que su mux haya sido eliminado, ni que deba borrarse. `G3Z3_UNLINKED_SERVICE_IN_GRID=PASS_1`; `G3Z3_RESIDUAL_ORIGIN=UNPROVEN`; `G3Z3_DELETE_AUTHORIZED=NO`. Próximo análisis: inspeccionar solo metadatos de muxes `mpegts/mux/grid` y relacionar el UUID del mux con el del servicio, sin divulgar direcciones/URLs/credenciales.


## G3-Z4 — servicio no asociado, deshabilitado y con mux existente

El operador realizó consultas GET de `channel/grid`, `mpegts/service/grid` y `mpegts/mux/grid`, sin mutación:

```text
SERVICIOS_SIN_CANAL: 1
MUXES_TOTALES: 2
MUX_EXISTE: True
SID_ES_3: False
SERVICIO_HABILITADO: False
CANAL_ASOCIADO_EN_SERVICE_GRID: False
TIENE_FECHA_CREACION: True
TIENE_ULTIMA_DETECCION: False
```

`G3Z4_UNLINKED_SERVICE=1`, `G3Z4_SERVICE_ENABLED=NO`, `G3Z4_SERVICE_MUX_EXISTS=YES`, `G3Z4_SID_EQUALS_3=NO`, `G3Z4_LAST_SEEN_NONEMPTY=NO`. Interpretar `False` de `bool(last_seen)` solamente como falsy (no garantiza nunca detectado). **No se demuestra** que el servicio corresponda al flujo eliminado `G3W Synthetic 3`. Tampoco se demuestra por simple conteo que el mux del canal 3 haya desaparecido, aunque queden 2 muxes.

Eliminación de servicios/muxes **NO AUTORIZADA**. Siguiente comprobación segura: establecer si el servicio deshabilitado comparte mux UUID con uno de los servicios aún enlazados a canales, a partir de las respuestas GET, publicando solo valores booleanos y recuentos, sin UUID, direcciones, URLs, nombres ni credenciales. Si lo comparte, es una razón adicional para no borrar por condición 'sin canal'.


## G3-Z5: servicio sin canal comparte mux con canal existente (2026-11-21)

Evidencia obtenida por el operador mediante solo GET a `channel/grid` y `mpegts/service/grid`:

```text
MUXES_CON_CANALES_ACTIVOS: 2
SERVICIOS_SIN_CANAL: 1
COMPARTE_MUX_CON_CANAL: True
```

Interpretación: el único servicio no vinculado a canales comparte `multiplex_uuid` con al menos un servicio que sí está vinculado a un canal. El servicio permanece deshabilitado según G3-Z4. Esto no prueba qué contenido representa ni su origen histórico, pero sí que **una poda de mux basada únicamente en la existencia de servicios huérfanos podría afectar a canales válidos**. También demuestra que 'servicio sin canal' no implica 'mux sin canales'. No eliminar servicios ni muxes. `G3Z5_SHARED_MUX=YES`; `G3Z5_SERVICE_DELETE_AUTHORIZED=NO`; `G3Z5_MUX_DELETE_AUTHORIZED=NO`.

Cierre de esta investigación preliminar: reconciliar **canales publicados** separadamente de la retención de servicios/muxes, y priorizar el siguiente gate con fixture que incluya CUID real, cambios de nombre, URL y grupo, y rastreo de identidad. El experimento actual G3-W no incluía CUID y no puede demostrar su persistencia.
