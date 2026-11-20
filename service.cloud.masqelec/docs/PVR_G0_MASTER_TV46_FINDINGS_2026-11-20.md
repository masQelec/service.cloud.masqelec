# G0 — laboratorio master, migración IPTV/PVR TV46 (20-11-2026)

Estado: **G0_PARTIAL — evidencia SQLite real + M3U develop; inventario TVH/JSON-RPC aún pendiente**.

## Alcance acordado

- Dispositivo piloto único: **master**. El operador dispone de backup del sistema Kodi. No habilitar cambios PVR para el resto de dispositivos hasta completar gates.
- Desarrollo: `masQelec/service.cloud.masqelec:develop` y `masQelec/cloud.masqelec:develop`. No publicar ZIP ni llevar a main antes de CI/piloto.
- La red TVH `IPTV LOCAL` refresca el archivo local cada 60 minutos. No sustituirla.
- Mantener limpieza de huérfanos existente hasta que la vía nativa o fallback verificado la sustituya.
- La M3U ya está publicada en `cloud.masqelec/develop/pvr/playlist.m3u`; no confundir esa publicación con una instalación en master.

## M3U develop, lectura del repositorio

Blob SHA GitHub: `97d728a0bbb0f325e5f8a71faa9a89eeba1fe5d7`.

- Cabecera `#EXTM3U`, 720 `#EXTINF`, 720 registros de stream; 26 grupos.
- `CUID`: 720 presentes y únicos, mínimo 1, máximo 11464 (no secuenciales).
- `tvg-chno` y `tvh-chnum`: 720 valores presentes y únicos por atributo; coinciden en los 720 registros, rango 1–720.
- `tvg-id`: 209 con valor, 198 valores únicos, 11 identificadores repetidos; no apto como clave exclusiva.
- La M3U NO debe ser copiada a fixtures, issues o logs por contener URLs de reproducción potencialmente privadas. En tests, generar datos sintéticos.

## Copia adjunta TV46.db (lectura offline)

SHA256 de los bytes analizados: `62431b9f0f17d7ffc4531514b73cb2c8dcfcd5ff784765afe9a6c40b053bfda5`. Tamaño: 282624 bytes. Lectura por URI SQLite `mode=ro&immutable=1` sobre el fichero adjunto; ningún cambio en el dispositivo master.

- Tabla `version` contiene `idVersion=46`, `iCompressCount=0`; `PRAGMA user_version=0`. El nombre TV46 no es la evidencia única de esquema: la fila de version sí da 46.
- `PRAGMA quick_check=ok`.
- `clients`: una instancia `pvr.hts` (`idClient=1`).
- `channels`: 865 canales TV del cliente 1, sin canales radio ni ocultos; todos tienen `iUniqueId`, sin duplicados por `(iClientId,iUniqueId)`.
- `channelgroups`: 40 filas: 38 grupos de cliente TV y 2 grupos internos (TV/radio).
- `map_channelgroups_channels`: 1715 asociaciones; ningún vínculo roto a `channels` ni `channelgroups`, ningún canal sin asociación.
- `timers`: 0; `providers`: 1.
- 17 valores de nombre de canal repetidos; **matching por `sChannelName` no es seguro**.
- Índice único en `channels(iClientId,iUniqueId)` y en tabla de mapeo `(idGroup,idChannel)`. No se observaron claves foráneas declaradas en las tablas inspeccionadas, lo cual NO demuestra ausencia de dependencias lógicas.
- `iUniqueId` no equivale a `idChannel` en los 865 registros. La semántica y vínculo de `iUniqueId` con TVH todavía debe confirmarse.

## Interpretación

La diferencia neta `865 - 720 = 145` NO prueba 145 bajas: es una migración de formatos e identidades. No inferir la correspondencia del CUID actual con CUID anterior o con IDs Kodi. No ejecutar purga por nombres ni por número de orden.

## Siguiente evidencia indispensable del master

1. Versión de Kodi y del addon `pvr.hts`; confirmar que la copia subida proviene de la DB efectivamente activa.
2. Snapshot filtrado READ-ONLY de red `IPTV LOCAL`, `channel/grid`, `mpegts/service/grid`, `bouquet/grid`, tags y DVR; omitir stream URL, tokens y credenciales.
3. PVR JSON-RPC Kodi (canales, client IDs, números, grupos) en una ventana temporal comparable con TVH tras su refresco de 60 min.
4. Demostrar mapeo entre `iUniqueId` de Kodi y UUID/IDs TVH, o clasificar ambiguos como bloqueantes.
5. Ensayar mecanismos nativos contra una baja sintética / piloto master antes de habilitar SQLite.
6. Con fallback SQL, primero backup SQLite consistente, exclusividad probada, dependencias/grupos internos preservados, transacción, integridad, rollback y verificación de reimportación.

## Gates

`G0_SQLITE_SNAPSHOT=PASS`
`G0_M3U_METADATA=PASS`
`G0_TVH_LIVE=WAITING`
`G0_KODI_JSONRPC=WAITING`
`G0_IDENTITY_MAPPING=WAITING`
`PVR_SQLITE_WRITE_AUTHORIZED=NO`
`PVR_FLEET_RELEASE_AUTHORIZED=NO`

Nota: el backup del sistema autoriza un piloto limitado por el operador, pero no prueba por sí mismo que SQLite esté libre de escritores ni que no se afecten grabaciones activas.
