# G3-X — auditoría de convergencia nativa, solo lectura (2026-11-21)

## Objetivo y estado

Preparar el reemplazo de la reconciliación agresiva de `lib/update_pvr.py` sin tocar de momento el algoritmo de mantenimiento que ya funciona en producción. El laboratorio G3-W acreditó 2→3→2 en Tvheadend y Kodi Ubuntu, con UUID e IDs de los canales conservados, pero **no prueba la ausencia de huérfanos de larga duración en CoreELEC**. Versiones: Ubuntu Kodi 21.3 + pvr.hts 21.2.6; CoreELEC Kodi 21.2.5 + pvr.hts 21.2.6.1.

## Auditoría del código legado

Revisado `lib/update_pvr.py` del branch `develop`:
- `_plan_reconcile` (desde línea histórica 608) lee `TVxx.db` y decide por nombre normalizado, no CUID ni identidad de servicio.
- `reconcile_kodi_channels_and_groups_with_playlist` (desde línea histórica 693) elimina registros SQLite de `channels`, `map_channelgroups_channels` y `channelgroups`, con `BEGIN IMMEDIATE`. Se impide operar con WAL/SHM pero no equivale a una garantía de coherencia de todo Kodi.
- `tvh_delete_channels_not_in_playlist_or_bad` (desde línea histórica 1403) elimina en TVH usando `idnode/delete` en función de nombre y bouquet, no CUID. Los 24 homónimos observados en el master hacen inviable demostrar identidad por nombre.
- `update_playlist` (desde línea histórica 1857) hace `pvr.hts` off → poda TVH → stop TVH → instala M3U atómica → modifica DB SQLite → modifica tags → start TVH → reenable `pvr.hts`; incluye reintentos de reinicio y limpieza posterior. La poda ocurre **antes** de instalar la nueva M3U, por lo que durante un cambio de lista puede operar sobre un estado inconsistente.
- G3-Q es solo una sombra de decisión; G3-W valida altas/bajas nativas en Ubuntu; **no se ha autorizado corte**.

## Cambio implementado (G3-X)

Se añadió `lib/pvr_native_convergence.py`, función pura `classify(tvh_rows,kodi_rows,tvh_total,kodi_total)`. Se ejecuta como sombra en `update_playlist()` **solo si el legado prevé soft reset**, antes de cualquier deshabilitación de `pvr.hts`, y obtiene:
- un único snapshot de `TVH /api/channel/grid` en GET;
- un único snapshot Kodi por `PVR.GetChannels(channelgroupid="alltv")` vía JSON-RPC de solo lectura;
- total comprobado contra el tamaño real de las listas, IDs no vacíos ni repetidos y nombres completos;
- multiconjunto de nombres, sin perder multiplicidad ni fusionar por coincidencia aproximada;
- identificación de duplicados que bloquean la interpretación como identidad.

Estados: `BLOCKED` ante datos incompletos, `DESCRIPTIVE_MISMATCH` si difieren, `DESCRIPTIVE_AMBIGUOUS` ante nombres repetidos o `DESCRIPTIVE_MATCH` si coinciden los nombres únicos. Todos devuelven `cuid_mapping_proven=False`, `native_orphan_removal_proven=False`, `delete_authorized=False` y `cutover_authorized=False`.

**Importante:** ni siquiera `DESCRIPTIVE_MATCH` acredita un vínculo `CUID → TVH UUID → Kodi channelid`. La API Kodi utilizada no devuelve CUID. Una coincidencia global entre 720 nombres puede ocultar la sustitución de un canal homónimo por otro. La auditoría tampoco acredita causalidad de refetch y no decide limpieza. No se registran nombres, URLs ni credenciales en los logs de G3-X.

**En esta fase no se han cambiado las llamadas destructivas del legado, las banderas de despliegue ni la configuración de CoreELEC.** Integrar sombra no significa que el comportamiento desplegado sea seguro; precisamente nos permite observar sin conmutar el mantenimiento.

## Pruebas

Nuevo `tests/test_pvr_native_convergence.py` incluye 16 tests: coincidencia, alta no propagada, baja con huérfano, convergencia descriptiva, nombres duplicados, conteos iguales pero distintos, paginación parcial TVH/Kodi, cero canales, IDs ausentes/repetidos, tipado estricto de totales, orden independiente, mayúsculas y prohibición permanente de mutaciones.

Ejecutar en Ubuntu:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/lib/pvr_native_convergence.py service.cloud.masqelec/lib/update_pvr.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_native_convergence.py' -v
```

El número de pruebas y el resultado de compilación están **pendientes de ejecución del operador**; los commits GitHub no equivalen a validación runtime.

## Siguientes gates

1. Obtener correspondencia no ambigua de CUID estable con servicios/muxes TVH y la identidad de backend que ve Kodi (no confiar en nombres).
2. Diseñar e instrumentar verificación temporal de refetch y convergencia en varios intervalos, con bloqueo explícito ante estados parciales.
3. Probar en laboratorio el caso de huérfanos históricos y fallos de red/lectura interrumpida.
4. Diseñar el mantenimiento de tags con propiedad demostrable, preservando los seis históricos.
5. Solo entonces modificar las rutas heredadas y probar el paquete completo. No ejecutar código de desarrollo en el master hasta pasar gates.
