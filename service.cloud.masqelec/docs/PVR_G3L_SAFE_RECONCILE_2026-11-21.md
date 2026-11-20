# G3-L — Reconciliador simplificado de categorías IPTV/PVR

Fecha: 2026-11-21, rama `develop`.

## Cambio de criterio aprobado

El objetivo operativo es que los **nombres de grupos y sus canales** concuerden con la M3U actual tras el refresco. No conservar UUID históricos de grupos vacíos a toda costa. G3-K demostró en master que `channeltag/create` no reutiliza el UUID solicitado; recuperó el inventario tras un ensayo temporal.

**No asumir** que TVH refresca por sí solo un grupo borrado que aún aparece en M3U: hace falta prueba con grupo temporal y sus asociaciones, no usar el grupo real para demostrarlo.

## Auditoría del código actual

`lib/update_pvr.py::sync_tvh_channel_tags_from_playlist` todavía crea ficheros manualmente con UUID aleatorios bajo la ruta de configuración TVH y elimina ficheros existentes con `os.remove`; tampoco distingue propiedad del addon. El módulo nuevo **no sustituye todavía ese flujo**: debe integrarse tras comprobar las llamadas reales, el registro persistente y los efectos en pvr.hts, sin activar el código anterior y el nuevo simultáneamente.

## Nuevo módulo aislado

`lib/pvr_tag_reconcile.py`: `reconcile_once(playlist, read_snapshot, post, owned_uuids=(), allow_delete=False)`. Consume inventarios TVH completos y coherentes y usa el planificador ya probado `lib/pvr_tag_plan.py`.

- Máximo **una** mutación TVH por ciclo.
- Prioridad de creación de grupos presentes en M3U, ausentes de TVH; `channeltag/create` por API, seguida de comprobación de UUID nuevo, unicidad y consistencia del inventario.
- Relectura de inventario antes de la mutación; bloquea drift, falta de convergencia, campos de tags ausentes, nombres/UUID ambiguos y enlaces incoherentes.
- Borra por `idnode/delete` solo UUID expresamente registrados como propiedad del addon, no internos, no presentes en M3U, sin canales enlazados y con `allow_delete=True`. El valor predeterminado es **False**.
- Jamás adopta automáticamente etiquetas históricas ni deduce propiedad por nombre, UUID o pertenencia a una playlist anterior.
- Devuelve nuevos UUID de propiedad para registrar de forma **durable y atómica**. No debe activarse borrado hasta implementar y verificar esa persistencia. Una creación por sí sola no asegura que TVH asigne los canales a la nueva etiqueta: comprobar por separado tras el refresco.
- No modifica índices de grupo, `TVxx.db`, ficheros `channel/tag` ni reinicia TVH/Kodi.
- No opera por sí mismo: requiere inyección explícita de `read_snapshot` y `post`, con autenticación y transporte existentes del addon.

`tests/test_pvr_tag_reconcile.py` contiene 13 pruebas sobre creación, idempotencia, propiedad, protección frente a canales activos, prioridad de creación, drift, inventario incorrecto, duplicados y respuestas fallidas.

## Validación local

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_reconcile.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_plan.py' -v
```

No se afirma PASS hasta recibir las salidas. La biblioteca sigue desconectada del mantenimiento automático y no altera producción.

## Gates de integración

1. Asegurar que `read_snapshot` enumera por completo `channeltag/grid` y `channel/grid` y que las operaciones API no se confunden con errores HTTP; comprobar compatibilidad con autenticación real del addon.
2. Añadir y probar registro persistente atómico de UUID propios; no auto-adoptar seis tags históricos.
3. Verificar en laboratorio o con un grupo desechable cómo se asignan los canales cuando se recrea el grupo, y reflejo en Kodi. Crear un tag vacío no basta.
4. Probar dos pasadas consecutivas sin cambios: cero escrituras en la segunda. Simular errores entre llamada API y respuesta, y asegurar bloqueo si hay ambigüedad.
5. Desactivar primero el sincronizador de ficheros antiguo antes de activar vía API, con rollback sencillo del addon sin tocar DB.
6. Solo entonces probar limpieza controlada de históricos bajo autorización específica; el código actual está en modo `allow_delete=False`.

**Producción, M3U, EPG, TVxx.db y ZIP: intactos.** CI/PR a main pendientes de validación de tests y puertas de integración.


## Resultado de pruebas confirmado por el operador

En Ubuntu, después de sincronizar `develop`, el operador confirma que ambos comandos de pruebas terminaron en `OK`:

- `test_pvr_tag_reconcile.py`: **13/13 OK**
- `test_pvr_tag_plan.py`: **13/13 OK**
- Total: **26/26 OK**

Esta confirmación cubre pruebas unitarias con datos de simulación; **no** valida la integración de escritura en Tvheadend real, ni el vínculo de canales a un grupo recreado, ni autoriza borrar grupos históricos. La integración automática sigue pendiente.

Próximo bloque **G3-M**: adaptador autenticado de inventario/API TVH, prueba de grupo temporal y verificación de asociación de canales y reflejo en Kodi, con operaciones de borrado de grupos históricos desactivadas. Evitar doble sincronizador de categorías.
