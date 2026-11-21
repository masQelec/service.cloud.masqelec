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
