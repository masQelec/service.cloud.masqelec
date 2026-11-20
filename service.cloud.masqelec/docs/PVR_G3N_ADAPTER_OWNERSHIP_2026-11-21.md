# G3-N — Adaptador TVH y registro de propiedad (entrega agrupada)

Fecha: 2026-11-21. Rama: `develop`.

## Situación observada

G3-L: operador confirmó 26/26 pruebas unitarias OK. G3-M: lectura real de TVH estable, 720 canales en M3U/TVH, 26 grupos M3U, 32 tags TVH, cero grupos ausentes, seis históricos vacíos/no propios preservados. 26 índices distintos de la M3U son informativos; no justifican reordenar Kodi.

## Implementación aislada G3-N

- `lib/pvr_tag_ownership.py`: registro JSON versionado de UUID **solo creados por nuestro nuevo flujo API**. Escritura atómica (archivo temporal 0600, `fsync`, `os.replace`, `fsync` del directorio); valida UUID hexadecimal de 32 caracteres, integridad del esquema, permisos privados y rechaza enlaces simbólicos. Un fichero inexistente dentro de un directorio privado equivale a registro vacío; un fichero presente corrupto bloquea. **No se autoadoptan** las seis etiquetas antiguas. No almacenar la lista de UUID en GitHub.
- `lib/pvr_tag_tvh_adapter.py`: adapta las funciones ya existentes `update_pvr._tvh_api_get_json` y `update_pvr._tvh_api_post_form`, que incorporan autenticación, a la interfaz `read_snapshot/post` de `pvr_tag_reconcile.reconcile_once`. GET exige HTTP 200, inventarios completos y límites. POST solo permite `channeltag/create` e `idnode/delete`, valida parámetros y errores devueltos.
- `tests/test_pvr_g3n_registry_adapter.py`: 15 tests para esquema, permisos, UUID, persistencia, errores HTTP, inventarios incompletos y listas de endpoints. La ejecución aún no está confirmada por el operador.

## Importante: no hay activación automática

Este bloque añade **piezas de soporte**, no conecta el escritor a `update_pvr.py`, no crea registros en el master, no escribe ni elimina tags TVH, ni toca `TVxx.db`, M3U o EPG. El flujo histórico con escrituras directas en `channel/tag` permanece tal como estaba: no asumir que ya ha sido sustituido.

**Pendientes antes de activar:**

1. Orquestador seguro con exclusión mutua y persistencia del UUID **después de cada alta**, con manejo de una caída entre API y persistencia. La pérdida de registro debe llevar a preservar un tag, no a adoptarlo/borrarlo silenciosamente.
2. Conectar las funciones autenticadas reales y validar respuesta de versiones de Tvheadend. No activar simultáneamente la sincronización antigua basada en archivos.
3. Comprobar que una categoría recién creada **recupera correctamente sus asociaciones de canales** tras el refresco real de M3U (la sola creación de un tag vacío no basta).
4. Validar que los datos TVH han convergido antes de cualquier borrado; integrar explícitamente el estado de Kodi sin escrituras SQLite.
5. Estudiar si las seis etiquetas históricas son realmente propias del addon antes de borrarlas (por ahora se preservan).

## Ejecución local agrupada

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3n_registry_adapter.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_reconcile.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_plan.py' -v
```

Esperados: 15 nuevos + 13 reconciliador + 13 planificador = **41 pruebas**. No afirmar PASS sin salida.

## Protocolo

Solo `develop`; ejecutar CI y revisión/PR a `main` cuando estén superados los gates de integración. El operador gestiona ZIP/publicación. Las seis categorías históricas y los 720 canales actuales no se modifican durante G3-N.


## Resultado de pruebas (confirmado por el operador)

El operador confirma `OK` en las tres baterías locales tras sincronizar develop:

- `test_pvr_g3n_registry_adapter.py`: 15 pruebas OK.
- `test_pvr_tag_reconcile.py`: 13 pruebas OK.
- `test_pvr_tag_plan.py`: 13 pruebas OK.
- **Total G3-N: 41/41 OK.**

Este resultado acredita solamente los tests locales; **no** confirma pruebas reales de escritura API, persistencia tras corte, recuperación de asociación canales/grupos, ni sustitución del sincronizador activo. No modificar `update_pvr.py` en producción ni ejecutar limpieza automática de las seis categorías históricas todavía.

**Próximo bloque G3-O**: integrar orquestación en develop, eliminar convivencia con el sincronizador de ficheros, controlar persistencia/caídas y ensayar asociación de canales a grupo por API tras refresco de M3U.
