# G2 — observación de huérfanos PVR en master

**Estado:** comparador implementado en `lib/pvr_inventory_observer.py`, pruebas sintéticas añadidas. **No conectado al servicio ni autorizado para borrar**.

## Semántica

Entrada: inventario TVH por UUID y número/grupos, inventario Kodi por pareja `(iClientId,iUniqueId)`, correspondencia **verificada externamente** `TVH UUID -> (iClientId,iUniqueId)`.

- Sin correspondencia: `BLOCKED_UNVERIFIED_CROSSWALK`.
- Si faltan UUID o hay mapeos repetidos: `BLOCKED_INCOMPLETE_CROSSWALK`.
- Con mapeo completo: `UNCHANGED` o `DIFFERENT`, con candidatos a huérfanos, faltantes y divergencia de número/grupos.
- En todos los casos: `destructive_operations_authorized=False`.
- **Ni nombre, ni orden, ni tvg-id ni CUID se presumen equivalentes a IDs internos.**
- Comparar solo canales de `IPTV LOCAL` y su instancia pvr.hts. Otros clientes, radio y grupos internos de Kodi no son huérfanos de esta fuente; el caller debe filtrar inventarios de forma comprobable.
- La disponibilidad de EPG es opcional y no interviene en reconciliación.

## Evidencia pendiente para conectar G2

1. Versión exacta de Kodi + pvr.hts y endpoint TVH soportado por master, con acceso solo lectura.
2. `channel/grid` y servicios de la red `IPTV LOCAL` sin streaming URLs, credenciales o nombres privados en trazas públicas.
3. `PVR.GetChannels`, `PVR.GetChannelGroups` y, cuando estén disponibles, IDs/propiedades del cliente. Confirmar interpretación del `iUniqueId` local mediante datos reales, no por similitud de número.
4. Acreditar que TVH terminó de refrescar la M3U y disponer de muestras estables de huérfanos.
5. Ensayo del mecanismo nativo sobre master, con protección de reproducción/grabación y restauración contrastada; no aplicar borrados SQLite antes de este gate.

## Validación

Pruebas añadidas: `tests/test_pvr_inventory_observer.py` (9 casos). Ejecutar junto a `test_pvr_playlist_metadata.py` y `test_pvr_g0_inspect_snapshot.py`:

```bash
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_*.py' -v
```

La presencia de tests en GitHub **no acredita su ejecución ni CI PASS**. El addon actual sigue usando el flujo histórico sin modificación. Los 720 canales de `cloud.masqelec/develop` no se deben purgar contra los 865 de TV46 por diferencia de nombres o índices.
