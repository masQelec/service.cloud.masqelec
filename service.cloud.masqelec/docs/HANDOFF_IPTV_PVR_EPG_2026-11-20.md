# Handoff — endurecimiento IPTV/PVR, Scan/Clean y EPG

**Fecha:** 2026-11-20  
**Código base:** `masQelec/service.cloud.masqelec` `main`, addon 2.3.2.  
**Trabajo siguiente:** desarrollar sobre `develop`, CI y pruebas sintéticas antes de PR a `main`.  
**Estado:** DISEÑO, ninguna playlist instalada ni cambio en TVH/Kodi/EPG o ZIP publicado.

## 1. Objetivo confirmado por el operador

- **IPTV Studio** genera la playlist M3U; se publica en el repositorio de configuración `masQelec/cloud.masqelec`, ruta `pvr/playlist.m3u` en la rama utilizada por los clientes (`constants.CLOUD_BRANCH='develop'`).
- Tvheadend **continúa usando su red IPTV automática** con archivo local `/storage/.user/playlist.m3u`, gestionado por el addon. **No cambiar el mecanismo de ingestión sin una prueba explícita**.
- `CUID` es un identificador **permanente e inmutable** para la identidad de cada canal, incluso al cambiar nombre, URL, grupo o número; no utilizar display name o orden como clave.
- Tvheadend es el gestor autoritativo de canales, muxes, servicios, grupos, numeración y EPG. Kodi recibe el resultado por `pvr.hts`. Evitar editar `TVxx.db` como mecanismo normal de reconciliación.
- Cambios de lista: incorporar altas, retirar bajas genuinas y modificar nombres/logos/orden/grupos/stream URL de los CUID ya existentes, sin borrar y recrear masivamente.
- EPG: `masQelec/epg` publica `guide.xml`; `tv_grab_file` lo sirve a TVH desde `https://raw.githubusercontent.com/masQelec/epg/main/guide.xml`. Validar carga y correspondencia con canales; no suponer que el addon genera la guía.
- No interrumpir reproducción o **grabaciones DVR de TVH** por cambios de playlist. Diferir operaciones disruptivas.
- Scan/Clean de Kodi: distinguir `APPLIED`, `UNCHANGED`, `DEFERRED`, `FAILED` y confirmar resultado real; no marcar éxito porque un método devolvió sin excepción.

## 2. Datos inspeccionados

**M3U publicada anterior** (consulta GitHub 20-11-2026): 865 `#EXTINF`, 26 grupos, `CUID=1..865` consecutivos, `tvg-chno=1..865`, 0 `tvg-id` con valor, nombres no únicos.

**Nuevo archivo adjunto** `playlist.m3u` del operador (inspección local): 720 `#EXTINF`, 26 grupos, 720 CUID distintos y presentes, 720 `tvg-chno` distintos, 720 `tvh-chnum` distintos, numeraciones coincidentes; `tvg-id` vacío en 511 registros y no único entre los presentes. Las diferencias requieren **MIGRACIÓN INICIAL**, no comparar CUID de dos generaciones como si los números antiguos fueran equivalentes. No incluir URLs IPTV ni credenciales en logs o issues.

La reducción 865 → 720 no permite concluir el número de bajas reales; puede incluir renombrados, reordenaciones y cambios de identidad entre formatos.

## 3. Auditoría del flujo actual (evidencia en código)

`lib/update_pvr.py::update_playlist()` compara plantilla remota y `/storage/.user/playlist.m3u`; si cambia o detecta mismatch en TVxx.db:
1. Deshabilita `pvr.hts` y espera; sondea TVH.
2. Determina bouquet IPTV; `_tvh_find_target_bouquet_uuid()` **elige el primer bouquet IPTV** cuando existen varios ambiguos.
3. Borra canales en TVH por nombre mediante `tvh_delete_channels_not_in_playlist_or_bad()`; también elimina canales sin nombre/Service01.
4. Para Tvheadend, instala playlist local y modifica **directamente** tablas `channels`, `map_channelgroups_channels`, `channelgroups` de `TVxx.db`.
5. Sincroniza `channel/tag` de TVH por nombres de `group-title` leyendo y borrando ficheros del addon de Tvheadend, arranca TVH, limpia otra vez, intenta EPG y rehabilita `pvr.hts`.

**Riesgos demostrables de diseño:**
- La comparación por nombre ignora identidad CUID; en la nueva M3U hay nombres duplicados.
- Los `CUID` antiguos se reutilizaban como posición: requieren tabla de equivalencias/adopción inicial con evidencia adicional.
- Escribir `TVxx.db` fuera del proveedor `pvr.hts` no garantiza que Kodi y TVH mantengan el mismo estado.
- Los grupos se comparan y crean por nombres ordenados alfabéticamente (los sets y `sorted` pierden el orden original de la M3U).
- No existe un mecanismo completo de altas + cambios + bajas + reorder verificado en TVH: se centran en limpieza/borrado.
- En `tvh_delete_channels_not_in_playlist_or_bad()` puede devolver `True` tras agotar rondas aun con restos; la verificación no condiciona siempre éxito.
- `_periodic_pvr_worker` ignora el resultado `(ok, did_something)`; Scan/Clean retornan booleanos ignorados y timestamps se avanzan sin confirmación.
- El soft-reset en arranque no verifica grabaciones activas de Tvheadend.
- `tvg-id` no es único ni existe para todos; matching EPG por nombre es fallback y puede producir colisiones.

**EPG observada:** `masQelec/epg/main/guide.xml` de unos 33 MB, commits recientes diarios (~01:00 CET), pero la corrección de XML y la programación de generación no han sido auditadas. El grabber `cloud.masqelec/pvr/tv_grab_file` usa la URL RAW correcta y entrega XML por stdout; TVH tiene `epggrab/internal/rerun` y autofix por nombre normalizado. No tocar la publicación EPG sin saber quién genera `guide.xml` y sin validar carga/rollback.

## 4. Diseño propuesto — primero validar comportamiento de TVH

**Fuente de verdad:** M3U versionada (CUID, URL, grupo, número, logo, tvg-id), persistencia de mapeos `CUID -> UUID de canal/mux/servicio de Tvheadend` si no se puede transportar CUID nativamente mediante la red automática. TVH es la autoridad de configuración aplicada; Kodi es lector PVR.

**Preflight sin efectos:**
- Descargar a staging privado, límite de tamaño/canales, `#EXTM3U`, pares `EXTINF + URL`, CUID únicos válidos, numeración válida y verificable, grupos, logos y placeholders de credenciales resueltos localmente; redacción de URLs en logs.
- Versionar hash M3U y manifiesto con recuentos/grupos, sin credenciales.
- Recuperar snapshot anterior válido; comparar por CUID y producir plan declarativo `add/update/remove/move/reorder/epg`, con diff resumido.
- Restringir borrados masivos, cambios de identidad y eliminación de grupos completos. **No inferir bajas por la discrepancia 865→720**, requiere validación inicial y adopción de IDs.
- Antes de aplicar: comprobar un único bouquet/una red IPTV identificada; si ambiguos, `BLOCKED_AMBIGUOUS_BOUQUET`.
- Consultar DVR de Tvheadend: grabaciones activas y programadas que puedan verse afectadas; además de reproducción Kodi. Sin garantías, aplazar.
- Usar modo `dry_run` por defecto en el primer ensayo. No editar SQLite Kodi ni los ficheros de tags en caliente; preferir APIs soportadas y/o operaciones nativas de la red IPTV. **Verificar en dispositivo la semántica exacta de la red auto IPTV**: cómo conserva muxes/canales, UUID, CUID, bouquets y numeración al modificar el archivo.

**Aplicación controlada:**
1. Detectar cambio de hash; si no cambió y TVH coincide, `UNCHANGED`.
2. Obtener lock local, snapshot/manifest de TVH/playlist/mapeos antes de modificar.
3. Aplicar diferencial o utilizar reload nativo de TVH solo si piloto demuestra que conserva identidades; conservar canales sin cambios.
4. Resolver bajas solo tras completar altas/modificaciones y límites de seguridad, con evidencia que los CUID realmente desaparecieron.
5. Grupos: mantener exactamente nombres y orden de primera aparición de la M3U, proteger grupos internos; comprobar miembros después de aplicar.
6. Numeración: `tvh-chnum` o `tvg-chno` validado, conservar orden y número único.
7. Validar número de canales, CUID asociados a UUID, grupos, iconos, URL hashes y posición **en TVH** antes de pedir actualización del cliente Kodi.
8. Kodi `pvr.hts` recupera la lista del servidor. Verificar con JSON-RPC/PVR API que canales y grupos coinciden antes de marcar `APPLIED`.
9. Si no hay grabaciones y es estrictamente necesario reiniciar TVH/PVR, hacerlo una vez con timeout, rollback y mantenimiento pendiente; nunca repetir bucles de reinicios.
10. Si la operación falla, no avanzar `applied_version`, conservar anterior y marcar `RECOVERY_REQUIRED` sin borrados repetidos.

**EPG independiente:** comprobar existencia y actualización de `guide.xml` en GitHub, esquema XMLTV y cobertura (IDs/canales/fechas). Crear correspondencia `CUID -> XMLTV channel id` sólo con IDs validados; mantener lista explícita de ambiguous/missing, conservar source anterior ante fallos. Importación TVH sin bloqueo ni reinicios repetitivos. No modificar el repo `masQelec/epg` durante esta fase de diseño.

**Scan/Clean:** estados separados del trabajo PVR: usar callbacks/eventos JSON-RPC para detectar inicio/fin y diferenciar no-op legítimo de timeout/fallo; no actualizar `_last_*_ts` ni resetear cooldown por error. Evitar que el nuevo motor PVR dependa de `VideoLibrary.Clean` (opera biblioteca de vídeo, no canales TV). Probar cada flujo por separado.

## 5. Gates para el siguiente chat

- G0: auditoría del entorno Tvheadend **real** (red IPTV auto, bouquet, tags, mapeo canal/mux/UUID, DVR y políticas de grabación) mediante export de configuración o APIs READ-ONLY; ningún secreto en logs.
- G1: parse M3U nuevo + fixture anterior + diff fiable basado en CUID; migración/adopción inicial supervisada.
- G2: simulador TVH con altas/bajas/renombre/move/orden, duplicados, streaming y fallos de API, **sin escritura directa en TVxx.db**.
- G3: PVR no-disruptivo: no ejecutar soft reset durante reproducción o grabación; escenarios de timers DVR.
- G4: EPG XMLTV y matching verificable, sin sobrescribir guía buena.
- G5: piloto real en un dispositivo con copia/snapshot, `dry_run` y rollback; confirmación del operador antes de aplicar borrados.
- G6: suite regresión + CI, PR `develop -> main`, preparación paquete Kodi por operador.

**Bloqueantes por confirmar al inicio:** configuración exacta y versión TVH en el dispositivo, cómo expone los IDs del mux/canal, la gestión DVR actual y si el usuario necesita preservar grabaciones programadas incluso cuando un canal se elimina. No inventar respuestas.

## 6. Prompt breve para otro chat

> Continuamos el proyecto `masQelec/service.cloud.masqelec` (CoreELEC addon 2.3.2). Lee `service.cloud.masqelec/docs/HANDOFF_IPTV_PVR_EPG_2026-11-20.md` y `README.md` en `main` antes de tocar código. Tvheadend usa red IPTV automática que lee `/storage/.user/playlist.m3u`, generada desde IPTV Studio y publicada en `cloud.masqelec`. `CUID` es ID estable; la nueva playlist contiene 720 canales y sustituirá a la anterior de 865 mediante **migración inicial controlada**. Objetivo: sync diferencial de canales/grupos/orden/logos/URLs, eliminación segura, TVH como autoridad y Kodi como espejo vía pvr.hts; EPG desde `masQelec/epg/main/guide.xml` con `tv_grab_file`. No borrar directamente TVxx.db, ni interrumpir grabaciones, ni publicar/instalar lista nueva sin gate. Empezar con auditoría de configuración TVH solo lectura, pruebas sintéticas y plan de migración. Mantener tests y documentación en GitHub.

## 7. Evidencia UI real de Tvheadend (HTML SingleFile 20-11-2026, 22:39–22:40)

El operador aportó tres capturas HTML guardadas de `Tvheadend` (vista Redes, edición de red y vista Paquetes/Bouquets). Lectura **sin acceso al equipo ni modificaciones**.

**Confirmado por los datos visibles:**
- Una sola red: `IPTV LOCAL`; fuente `file:///storage/.user/playlist.m3u`.
- Estadísticas de la red: **865 multiplexores, 865 servicios y 865 canales mapeados**.
- Vista Paquetes/Bouquets: fila `IPTV LOCAL`, source `iptv-network://cce41e6f2d9b5d829d3af38159eea0a5`; **865 services seen** y **865 services**.
- Los demás paquetes DVB fastscan listados tienen 0 servicios vistos; no se debe inferir que todos los 14 bouquets son redes IPTV activas.
- La configuración de edición expone el campo URL local y opciones de numeración/escaneo, pero el texto extraído no acredita el estado efectivo de todos los checkboxes; comprobar sus valores por API antes de decidir algoritmo.

**Implicación:** mantener la red `IPTV LOCAL` y su bouquet existentes; no crear otra red ni borrar indiscriminadamente. No existe evidencia todavía de cómo la red auto IPTV empareja un M3U nuevo con mux UUID antiguos, ni de que reconozca `CUID` nativamente. Exigir snapshot por API READ-ONLY de network/grid, mpegts/mux/grid, mpegts/service/grid, channel/grid, bouquet/grid y DVR antes de habilitar borrados o renumeraciones. Evitar publicar identificadores de sesiones, credenciales o URLs privadas; la URI de origen es local.

## 8. Corrección de alcance por el operador — TVH ya sincroniza cada 60 minutos

**Aclaración funcional confirmada:** Tvheadend lee automáticamente la M3U local cada **60 minutos**, incorpora los canales de la lista y mantiene su orden correcto. El usuario señala que la incidencia real está **en Kodi y su base de datos de TV**, no en la importación de la playlist por TVH. La auditoría/diseño debe priorizar la propagación `Tvheadend -> pvr.hts -> TVxx.db/Kodi`, evitando rediseñar un mecanismo TVH que ya funciona para este caso.

**Nueva prioridad:** verificar por API en modo lectura si el inventario de TVH es correcto y si el inventario PVR/orden/grupos visto por Kodi diverge. No confiar en diferencias por nombre para concluir un canal ausente: correlacionar UUID/PVR channel unique ID según interfaces disponibles. Antes de escribir código, validar cómo `pvr.hts` recibe notificaciones de cambios y qué operaciones soporta realmente (refresh/reconnect/toggle), incluidos tiempos, seguridad durante reproducción/grabación y persistencia de agrupaciones.

**Cambios propuestos al mantenimiento:** (1) impedir la edición directa recurrente de tablas `TVxx.db` (`channels`, `channelgroups`, `map_channelgroups_channels`) como mecanismo habitual de actualización de PVR; (2) separar actualización de playlist/TVH de reconciliación Kodi; (3) no reiniciar TVH cuando la discrepancia solo existe en Kodi; (4) recuperación escalonada por `pvr.hts` **únicamente** tras confirmar fallo persistente y ausencia de condiciones que la vuelvan disruptiva; (5) verificar el estado final antes de marcar éxito y mantener estado `DEFERRED` o `FAILED` si Kodi no coincide. `VideoLibrary.Scan/Clean` pertenecen a películas/series, no a la base de canales PVR.

**No probado aún:** que todos los CUID, grupos y números de la nueva playlist se representen correctamente en TVH tras el primer ciclo de 60 minutos; que Kodi pueda resincronizar sin toggle; mecanismos de notificación de cambios de la versión exacta de `pvr.hts` y TVH. Esto requiere una comprobación READ-ONLY y ensayos en un piloto, no afirmaciones genéricas.
