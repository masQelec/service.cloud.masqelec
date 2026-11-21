# G3-Z — Inspección estructural de servicios Tvheadend (2026-11-21)

## Evidencia previa

G3-W comprobó 2→3→2 en TVH y Kodi Ubuntu, conservando los identificadores originales. G3-Y obtuvo, por lectura real del laboratorio, dos entradas en ambos sistemas. La API `/api/channel/grid` de TVH expone `services` como lista, además de `uuid`. Kodi `PVR.GetChannels` expone `channelid`, pero no la identidad de backend o CUID. El fixture G3-W no incluye CUID. Ningún nombre, número ni orden acredita una relación CUID→TVH→Kodi.

## Nuevo probe y pruebas

`tools/pvr_g3z_tvh_service_shapes_lab.py` hace una **única lectura GET** de `http://127.0.0.1:19981/api/channel/grid?start=0&limit=20000`. No consulta CoreELEC, SQLite ni Kodi; no escribe TVH. Comprueba completitud y UUID no vacío, e inspecciona exclusivamente las **formas de los elementos** en el campo `services`. Imprime tipos, nombres seguros de claves si son objetos y recuentos. No imprime UUID de servicios, URLs, nombres de canales ni tokens.

Este ensayo es de descubrimiento. No pretende todavía recuperar el identificador único del servicio ni autorizar reconciliaciones. Los campos `cuid_mapping_proven`, `tvh_to_kodi_identity_proven` y `deletion_authorized` permanecen en `NO`.

Se crearon 10 pruebas unitarias en `tests/test_pvr_g3z_tvh_service_shapes_lab.py`: formas de referencia, datos sensibles ausentes de la salida, inventarios truncados, servicios no listados, UUID ausentes, claves de objeto inesperadas y bloqueo de eliminación. **Los tests están pendientes de ejecución real**.

## Instrucciones Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/tools/pvr_g3z_tvh_service_shapes_lab.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3z_tvh_service_shapes_lab.py' -v
python3 service.cloud.masqelec/tools/pvr_g3z_tvh_service_shapes_lab.py
```

Basta que TVH del laboratorio siga activo en 19981; no hace falta abrir Kodi para este ensayo. No efectuar reconfiguración del IPTV master. El diagnóstico se bloquea ante datos API parciales.

## Siguiente paso

Conocer si las referencias `services` son UUID, cadenas descriptivas u objetos permite decidir qué API de solo lectura puede identificar la configuración y persistencia de servicios/muxes TVH. Solo después diseñaremos el fixture con CUID y una prueba longitudinal de identidad. No dar por demostrado un vínculo de backend de Kodi por su `channelid`.


## G3-Z, resultado real comunicado por operador (2026-11-21)

```text
Ran 10 tests in 0.000s
OK
G3Z=SHAPES_ONLY
STATUS="TVH_SERVICE_REFERENCE_SHAPES_ONLY"
CHANNELS=2
CHANNELS_WITH_NO_SERVICES=0
SERVICE_REFERENCES=2
REFERENCE_SHAPES={"str": 2}
CUID_MAPPING_PROVEN="NO"
TVH_TO_KODI_IDENTITY_PROVEN="NO"
DELETION_AUTHORIZED="NO"
MASTER_TOUCHED="NO"
```

`G3Z_UNIT=PASS_10`; `G3Z_SERVICE_SHAPES=PASS`. Las dos referencias son cadenas, pero este resultado por sí solo no prueba que sean UUID válidos de objetos de servicio, que resuelvan en `service/list`, ni que puedan vincularse a CUID o a Kodi.

La documentación oficial de la API Tvheadend describe `channel/grid.services` como referencias a servicios mediante UUID y `service/list?enum=1` como un inventario de pares `key`/`val` (donde `key` es el identificador de servicio). El próximo gate debe **comprobar efectivamente** que todas las referencias de los canales sintéticos resuelven en el inventario de servicios, sin divulgar valores privados ni utilizar ese resultado para hacer un mapeo a Kodi.
