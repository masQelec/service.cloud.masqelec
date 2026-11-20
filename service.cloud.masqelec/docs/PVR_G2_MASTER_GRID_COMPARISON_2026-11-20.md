# G2 master — comparación real TV46 vs channel/grid (20-11-2026)

**Evidencia:** copia aportada por el operador `TV46.db` y export `grid.json` de GET `/api/channel/grid`. Ambos analizados **sin escribir SQLite, sin API de escritura y sin tocar master**.

## Identificación y completitud

- Export TVH `grid.json`: SHA256 `29927e4a93d6dec5dd5ea6409625b21a0d849e3842e84be448a6bba8d0c4d121`; `total=865`, `entries=865`, 865 UUID diferentes, 865 números diferentes (1–865), 865 canales habilitados, todos en el mismo bouquet.
- DB Kodi: esquema TV46 (`version.idVersion=46`), 865 canales, un cliente `pvr.hts` (`iClientId=1`), 38 grupos cliente y dos grupos internos TV/radio.
- `PRAGMA quick_check=ok` en copia SQLite (auditoría anterior).
- 845 nombres diferentes en TVH y 845 en Kodi; hay duplicados. Los multiconjuntos de nombres coinciden exactamente, **pero los nombres NO son IDs estables**.
- Se emparejan 828 nombres que aparecen exactamente una vez en cada inventario. Son **pistas** para investigación, no correspondencias de identidad aprobadas.
- Cruce independiente `(nombre, número)`: los 865 pares del TVH aparecen exactamente en el grupo interno TV de Kodi. Ni faltantes ni sobrantes por esa comparación. Las columnas `map_channelgroups_channels.iChannelNumber` e `iClientChannelNumber` concuerdan con el número TVH para los 828 nombres únicos; `iOrder` no equivale a número.
- No hay prueba de que `channels.iUniqueId` en Kodi equivalga a UUID, número o CUID TVH: los 828 casos de nombre único NO hacen coincidir `iUniqueId` con número.
- Clasificación segura: `channelgroups.idGroup=1` es un grupo *real* (`iGroupType=0, iClientId=1`); grupos internos `Todos los canales` están en IDs 27/28 (`iGroupType=1, iClientId=-1`). No codificar IDs internos fijos.

## Conclusión

**G2_SNAPSHOT_OLD_INVENTORY_CONSISTENT=PASS (por nombre+número; no identidad técnica).** El archivo `grid.json` contiene todavía los **865 canales de la generación anterior**, al igual que la copia `TV46.db`. Por ello NO sirve todavía para demostrar el fallo de canales huérfanos tras reemplazar la M3U. La nueva M3U de `cloud.masqelec/develop` tiene 720; **no interpretar 865-720 como 145 bajas demostradas**.

**G2_UUID_TO_KODI_UID=UNVERIFIED**; **G2_POST_MIGRATION=NOT_CAPTURED**; **SQLITE_WRITE=BLOCKED**.

## Próximo gate en master

Una vez se haga una migración explícitamente autorizada en piloto y Tvheadend haya terminado su refresco de 60 minutos, tomar en la misma ventana:
1. Nuevo `channel/grid` completo de la red `IPTV LOCAL`, con `total == len(entries)`.
2. Nuevo inventario Kodi JSON-RPC/PVR y copia SQLite coherente, identificando base activa y controlando que no haya escritores durante snapshot.
3. Verificar identidad mediante HTSP/provider `channelId` y `iUniqueId` Kodi, sin depender de nombre ni número. Si no puede validarse, registrar `BLOCKED_UNVERIFIED_CROSSWALK`.
4. Probar recuperación nativa de `pvr.hts` sobre master; si deja huérfanos y hay equivalencia comprobada, preparar fallback SQLite transaccional con backup, exclusividad y rollback.

La cobertura EPG no es parte del gate. No publicar `grid.json` bruto, URLs de stream ni credenciales en GitHub.
