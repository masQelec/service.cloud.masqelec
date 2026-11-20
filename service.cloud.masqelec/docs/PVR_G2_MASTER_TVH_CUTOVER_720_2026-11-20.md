# G2 — corte real de IPTV LOCAL: 865 → 720 (20-11-2026)

**Rama de desarrollo:** `develop`. **Alcance:** auditoría sin escritura, sin cambios en Tvheadend/Kodi, playlist, EPG o ZIP.

## Fuentes inspeccionadas

Dos exportaciones de la API real `GET /api/channel/grid?start=0&limit=20000`, aportadas por el operador:
- Antes: `grid.json`, SHA-256 `29927e4a93d6dec5dd5ea6409625b21a0d849e3842e84be448a6bba8d0c4d121`, 484185 bytes.
- Después: `new_grid(1).json`, SHA-256 `d4182d43e3fb9aca1ecc8c8e95f9aea799f0707a52a3da56647eefc1645e3f5a`, 403372 bytes.

**No subir las exportaciones brutas al repositorio.** El análisis se limita a conteos de campos y conjuntos de identificadores, sin divulgar URLs privadas ni nombres completos.

| Propiedad | Antes | Después | Intersección |
|---|---:|---:|---:|
| `total` = longitud `entries` | 865 | 720 | — |
| UUID canal únicos | 865 | 720 | **0** |
| UUID servicio (`services`, tuplas) únicos | 865 | 720 | **0** |
| Números únicos | 865, 1–865 | 720, 1–720 | 720 **números, no identidades** |
| Nombres diferentes | 845 | 707 | **0 exactos** |
| Valores de nombre repetidos | 17 | 11 | — |
| Habilitados | 865 | 720 | — |
| Bouquet único por captura | 1 | 1 | Mismo bouquet |

## Interpretación técnica

1. La actualización a la nueva M3U está reflejada en la **API de canales** de Tvheadend: 720 entradas activas, sin UUID/números duplicados y con numeración completa 1–720.
2. Se ha producido **sustitución de toda la generación de UUID de canal y UUID de servicio**. La coincidencia en número **no es prueba de identidad**. La nueva generación incluye nombres renombrados, con prefijos eliminados.
3. `grid.json` carece de una correspondencia verificada `CUID → TVH service/channel UUID → Kodi (iClientId,iUniqueId)`. No hay base para atribuir 145 bajas reales ni para eliminar 865 canales de Kodi automáticamente.
4. Los `tags` comparten 20 UUID entre generaciones (26 valores de etiquetas en cada captura), pero **son identificadores de grupos, no de canales**. No usar estos grupos como equivalencia de identidad.
5. La copia antigua `TV46.db` tiene 865 canales: es evidencia **PRE-corte**. No representa el estado actual de Kodi.
6. La ausencia de `tvg-id` en parte de la lista nueva no autoriza bajas: EPG es opcional.

## Gates

- `G2_TVH_GRID_720_COMPLETE=PASS` (sobre el export, no acredita reproducción).
- `G2_TVH_OLD_TO_NEW_UUID_OVERLAP=0`.
- `G2_TVH_OLD_TO_NEW_SERVICE_OVERLAP=0`.
- `G2_POST_CUTOVER_KODI_DB=MISSING`.
- `G2_CUID_TVH_KODI_CROSSWALK=UNVERIFIED`.
- `G2_SQLITE_WRITE=BLOCKED`.
- `G2_RELEASE=BLOCKED`.

## Siguiente verificación obligatoria

Obtener una **nueva copia consistente** de la base `TVxx.db` activa de Kodi **tras el cambio** (no reutilizar la anterior), con versión, WAL y journal controlados; y, preferentemente, un inventario PVR JSON-RPC tomado en la misma ventana. Ejecutar el observador en modo lectura sobre esa copia y la exportación de 720. Medir canales Kodi, duplicados, grupos internos/externos y referencias; **no declarar huérfanos verificados por mero conteo o nombre**. Investigar fuente real del `iUniqueId` de `pvr.hts` a partir de HTSP y versión instalada antes de autorizar bajas.

### Regla de seguridad específica de este corte

**No aplicar el reconciliador histórico basado en nombres** a esta migración: el cambio simultáneo de nombre, número, UUID de canal y UUID de servicio hace que el algoritmo no pueda discriminar renombrados de altas/bajas. Mantener la capacidad de limpieza futura, pero continuar con plan sin escrituras hasta verificación de identidades y recuperación.
