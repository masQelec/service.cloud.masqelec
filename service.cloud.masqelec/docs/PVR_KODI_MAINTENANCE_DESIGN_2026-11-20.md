# PVR / KodiELEC — especificación de endurecimiento y traspaso

**Estado: diseño aprobado en objetivos, implementación pendiente.** Fecha: 20-11-2026.  
**Proyecto:** `masQelec/service.cloud.masqelec`, versión actual del addon 2.3.2.  
**Fuente histórica de auditoría:** [HANDOFF_IPTV_PVR_EPG_2026-11-20.md](HANDOFF_IPTV_PVR_EPG_2026-11-20.md).  
**Regla de precedencia:** si el documento histórico y este difieren, prevalecen las **aclaraciones posteriores del operador y esta especificación**, sin confundir propuestas con comportamientos ya probados.

## 1. Resultado final exigido

El addon debe mantener IPTV/PVR de manera **eficaz, fiable, no destructiva, verificable y repetible**:

- IPTV Studio publica una M3U en GitHub; **CUID** identifica cada canal de manera permanente e independiente de nombre, URL, logotipo, grupo, posición y número.
- El addon descarga e instala la M3U local en `/storage/.user/playlist.m3u`, con credenciales obtenidas del fichero privado del equipo. **Nunca subir una M3U resuelta con credenciales a GitHub ni registrar URLs privadas.**
- **Tvheadend funciona correctamente** con una sola red IPTV automática `IPTV LOCAL` que lee `file:///storage/.user/playlist.m3u`, revisa cada **60 minutos**, incorpora los canales y respeta su orden. **No reconstruir su inventario ni añadir otro motor de sincronización TVH por defecto.**
- La incidencia que **sí observa el operador** está en Kodi: `pvr.hts` incorpora canales nuevos, pero **conserva canales retirados de Tvheadend** en su inventario/base PVR. El addon actual realiza una limpieza compensatoria en `TVxx.db` comparando lista y registros.
- Se **mantiene el objetivo indispensable de borrar huérfanos de Kodi** y depurar relaciones/grupos obsoletos. No se debe eliminar esa capacidad bajo el argumento de evitar SQLite. Primero probar una vía nativa de Kodi/pvr.hts, si existe y funciona; si no, diseñar **intervención SQLite segura** basada en inventario real, versión y esquema.
- Tras la actualización, Kodi debe coincidir con Tvheadend en canales presentes, números, orden y grupos, sin modificar innecesariamente las entradas conservadas, sin afectar grabaciones y con recuperación acotada ante errores.
- EPG en repositorio separado `masQelec/epg`, `guide.xml`, consumida por `tv_grab_file` desde `https://raw.githubusercontent.com/masQelec/epg/main/guide.xml`; conservar gestión de EPG y corregir solo pérdidas/errores comprobados.
- **VideoLibrary.Scan/Clean** de películas y series es **otro mantenimiento**, independiente de los canales TV/PVR; endurecer sus confirmaciones sin mezclarlos.

## 2. Datos de referencia y hechos ya observados

| Elemento | Datos comprobados |
| --- | --- |
| Playlist antigua publicada | 865 entradas, 26 grupos, CUID consecutivos 1–865 y numeración consecutiva, sin tvg-id |
| Nueva M3U facilitada por operador | 720 entradas, 26 grupos, 720 CUID únicos (no correlacionar CUID antiguo posicional con identidad nueva); usa tvh-chnum, tvg-chno y algunos tvg-id |
| UI TVH guardada (3 HTML) | Una red `IPTV LOCAL`, 865 multiplexores, servicios y canales mapeados; bouquet IPTV LOCAL; fuente local M3U |
| Intervalo TVH | Revisión automática cada 60 minutos, según confirmación del operador |
| Fallo observado | Kodi agrega nuevos y conserva antiguos; el problema está en Kodi/TVxx.db, no en el refresco automático de TVH |
| Periodicidad addon | `pvr_update_period_hours`=12 por defecto; `update_pvr` en arranque y `update_playlist` en mantenimiento inicial/periódico |
| EPG | Github `masQelec/epg/main/guide.xml`, grabber en `cloud.masqelec/pvr/tv_grab_file`, publicación diaria observada anteriormente |

**No comprobado aún:** versión/esquema exactos de `TVxx.db` de los equipos, APIs nativas de resincronización de la versión específica de Kodi/pvr.hts, si `CUID` viaja a TVH/Kodi, nombres duplicados como colisiones reales, correspondencias EPG y tolerancia de grabaciones ante deshabilitar `pvr.hts`. No inventar datos ni afirmar que un método está probado.

## 3. Código actual: diagnóstico que debe guiar la refactorización

Archivo `service.cloud.masqelec/lib/update_pvr.py` (2.248 líneas auditadas en main) y `service.py`.

1. `update_playlist()` descarga la plantilla, la resuelve con credenciales locales y compara hash con el archivo instalado; `_plan_reconcile()` revisa nombres de `TVxx.db` para detectar sobrantes.
2. Ante M3U nueva o mismatch, deshabilita `pvr.hts`, y **borra canales de TVH basándose en la playlist antigua**, pues `tvh_delete_channels_not_in_playlist_or_bad()` se llama antes de instalar `new_playlist`. Este borrado puede oponerse a la actualización automática correcta de TVH. **Eliminar la dependencia de este paso destructivo**, manteniendo aparte medidas contra canales basura comprobadas y acotadas.
3. Para Tvheadend, instala la M3U local por `os.replace`, y `reconcile_kodi_channels_and_groups_with_playlist()` borra filas de `map_channelgroups_channels`, `channels`, `channelgroups`. Este borrado por nombre **sí persigue la incidencia real**, pero carece de identificación robusta, cobertura de esquema, estado verificado y transacción global de rollback.
4. `reconcile...` se niega a escribir si existen `TVxx.db-wal` o `-shm`; ello **no acredita** por sí solo si la DB está cerrada. Si retorna `False`, `update_playlist()` lo ignora y continúa.
5. `_pick_tv_db_path()` elige ordenando nombres de ficheros de forma lexicográfica; hay que descubrir la DB **realmente activa** de la versión de Kodi instalada.
6. `_wait_pvr_ready()` solo comprueba PVR disponible y *algún* canal, no equivalencia completa de Tvheadend y Kodi.
7. `update_playlist()` tiene rutas que devuelven `(True,True)` incluso si TVH no volvió a READY o la recuperación PVR falló. `service.py::_periodic_pvr_worker()` **ignora el booleano `ok`** y marca éxito; arranque también registra finalizado sin comprobarlo.
8. `_plan_reconcile()` solo detecta canales/grupos sobrantes por nombres normalizados; no detecta ausencia de altas, numeración incorrecta ni asociaciones/orden, y con nombres duplicados puede conservar huérfanos.
9. `sync_tvh_channel_tags_from_playlist()` opera sobre ficheros de configuración TVH y usa `sorted` sobre grupos, lo que puede divergir del orden M3U. Confirmar qué parte de este proceso sigue siendo imprescindible antes de tocarla.
10. La validación de M3U remota no realiza validación completa de formato, número de canales, CUID únicos, tamaño mínimo relativo ni límites para borrados masivos.
11. El procedimiento incluye stop/start TVH, múltiples toggles de pvr.hts y reinicio Kodi opcional, con protecciones insuficientes ante grabaciones TVH.
12. Los tests generales en `tests/` cubren mayormente rclone y catálogo; **no hay suite de integración PVR/SQLite adecuada**. CI en verde no acredita el comportamiento PVR.

**Conclusión:** hay que preservar el mantenimiento compensatorio de Kodi, pero eliminar estados falsos y efectos secundarios contra Tvheadend; no dar por hecho que prescindir de SQLite resuelve el problema.

## 4. Diseño objetivo, sin modificar producción

### 4.1 Modelo de datos y verificación

- **Dos inventarios:** fuente `Tvheadend channel/grid` (inventario final real; incluir UUID, número, nombre, tags/grupos, servicios) y destino `Kodi` (JSON-RPC PVR y, si procede, lectura de la DB activa).
- La M3U establece intención `CUID + propiedades + grupos/orden`; la correspondencia `CUID → TVH UUID/servicio → ID de Kodi` se construirá **solo si los identificadores están disponibles y verificables**; nunca asumir que TVH conoce CUID.
- Detectar duplicados, identidad ambigua, variaciones masivas y cambios fuera del bouquet administrado. **Bloquear operaciones destructivas si falta una correspondencia inequívoca.**
- Comparar `actual vs esperado` después de completar el refresco TVH; si TVH aún no terminó su ciclo de 60 min, **DEFERRED**, no limpiar Kodi contra inventario intermedio.

### 4.2 Reconciliación Kodi

1. `PRECHECK`: M3U válida, red TVH concreta, snapshot consistente, grabaciones y reproducción, salud del PVR.
2. `PLAN`: identificar en Kodi canales huérfanos que ya no existen en TVH, grupos huérfanos, orden/números divergentes y altas pendientes. Resumen de cambios **sin secretos**.
3. `NATIVE_FIRST`: comprobar si un mecanismo soportado por esta versión de Kodi/pvr.hts elimina los huérfanos sin manipulación DB, con una prueba controlada. **No dar por funcional hasta verificar**.
4. `SQLITE_FALLBACK` solo si es necesario: realizar copia consistente/backup, identificar DB en uso, garantizar exclusividad, inspeccionar esquema y relaciones, iniciar transacción, eliminar exclusivamente huérfanos verificados, comprobar integridad y **rollback**; no borrar filas por coincidencia de nombre con la playlist.
5. `RECONNECT`: reactivar pvr.hts solo si se ha detenido y hace falta; evitar reiniciar TVH si el problema es Kodi.
6. `VERIFY`: volver a comparar TVH y Kodi (incluidos grupos/números). Solo declarar `APPLIED` si converge, `UNCHANGED` si ya coincidía, `DEFERRED` si existen actividades protegidas, `FAILED` si no convergió, `RECOVERY_REQUIRED` si no se pudo restaurar.
7. `COMMIT`: avanzar última versión y timestamp **solo tras verificar**, con lock y journal local de operaciones pendientes; evitar loops de restablecimiento.

**Importante:** no alterar el comportamiento que ya funciona de altas y orden en TVH. No limpiar indiscriminadamente `channels` ni `channelgroups`; proteger otras fuentes PVR, grupos internos, favoritos y grabaciones vinculadas. Una limpieza SQL de 3 tablas **no es aceptable sin contrastar dependencias en la versión de Kodi**.

### 4.3 Coordinación de intervalos y arranque

- TVH refresca cada 60 minutos; addon revisa cada 12 horas por defecto. Resolver esta asincronía explícitamente: no limpiar la DB antes de que TVH haya consumido la nueva M3U.
- Comprobar en arranque sin forzar reinicios automáticos que interrumpan TVH; reconocer `DEFERRED` si está procesando, grabando o reproduciendo.
- Reintento con backoff, máximo de rescates acotado, mutex y tiempos límite. No afirmar éxito por falta de excepción.
- Mantener el mantenimiento de EPG desacoplado del ciclo de eliminación de huérfanos.

### 4.4 EPG y Scan/Clean

- EPG desde URL RAW; comparar versión/frescura, validar guía XMLTV y correspondencia de fuentes sin forzar reload global tras cada reconexión PVR. Si la fuente no ha cambiado y TVH tiene EPG correcto, `UNCHANGED`.
- `VideoLibrary.Scan/Clean`: pruebas independientes sobre API Kodi; no marcar timestamp ni resetear contador de fallos cuando `update_library_silent`/`clean_library_silent` devuelve fallo/timeout. Registrar inicio/fin de operación y estado de resultado; comprobar que no está bloqueado por reproducción/montajes.

## 5. Plan de implementación con gates obligatorios

| Fase | Entrega verificable | Gate antes de avanzar |
| --- | --- | --- |
| G0: lectura real | Versiones, snapshots TVH/Kodi, SQLite schema; 2–3 huérfanos que existan en Kodi y no TVH | Evidencia concreta + autorización de alcance |
| G1: parser y diff | Fixtures M3U vieja/nueva, CUID únicos, grupos, orden, planes sin secretos | Tests de nombre duplicado, renombre, movimiento, URL, bajas |
| G2: observador PVR | Comparación TVH→Kodi sin escritura, estados tipados, logs redactados | Detecta huérfanos y no modifica TVH/SQLite |
| G3: mecanismo nativo | Ensayo controlado de refresco del PVR y evaluación de huérfanos | Adoptar solo si elimina obsoletos, preserva grupos/orden |
| G4: SQLite seguro si es imprescindible | Copia/backup, schema gate, lock, journal, transacción, rollback | Tests de WAL, DB incorrecta, fallo medio-borrado, integridad |
| G5: aplicación y recuperación | Reconciliación sin reinicios TVH innecesarios; protección DVR | Verificar TVH↔Kodi, backoff y reintentos limitados |
| G6: EPG y Scan/Clean | Validación independiente, no alterar guías buenas | Pruebas de EPG ausente/ambiguo, Scan/Clean timeout |
| G7: piloto | Dispositivo controlado, M3U de prueba, comparación antes/después, grabaciones | Aprobación del operador; **no desplegar flota** sin PASS |
| G8: integración | Docs actualizados, CI, PR develop→main | PASS completo, ZIP lo publica el operador |

## 6. Prohibiciones y seguridad

- **No cambiar todavía** la lista en GitHub, la M3U de ningún equipo, la configuración TVH, EPG ni el ZIP; no tocar producción durante auditoría y simulaciones.
- **No eliminar** la limpieza de huérfanos de Kodi sin sustituto verificado, ni sustituirla por un reset general de la base de datos.
- **No modificar TVxx.db en caliente**, ni inferir exclusividad solo porque WAL/SHM no existen.
- **No eliminar canales de TVH basándose en los nombres de una playlist antigua**, ni elegir bouquets ambiguos.
- No exponer credenciales IPTV, URLs privadas, claves TVH ni datos de logs. Redactar en fixtures y salidas.
- No generar éxito cuando TVH, PVR, reconciliación o verificación final han fallado.

## 7. Primera recogida de datos en otro chat

Solicitar una **captura read-only** (scripts y comandos concretos adaptados a CoreELEC) que obtenga: versión Kodi, Tvheadend y pvr.hts; canales/grupos y UUID TVH de `IPTV LOCAL`; canales/grupos/orden desde JSON-RPC Kodi; ruta y versión de `TVxx.db` realmente activa; columnas, índices y claves foráneas sobre copia segura; y ejemplos de registros huérfanos. **No exigir contraseñas ni archivos privados**. El addon no puede inventar un mapeo de CUID hacia Kodi.

Si no existen huérfanos actualmente, crear primero una reproducción sintética/laboratorio, no borrar un canal real en producción para forzar la prueba.

## 8. Prompt para iniciar el próximo chat

> Vamos a endurecer el mantenimiento IPTV/PVR del addon `masQelec/service.cloud.masqelec`. Empieza leyendo `service.cloud.masqelec/docs/PVR_KODI_MAINTENANCE_DESIGN_2026-11-20.md` en `main` y, si necesitas las trazas, `docs/HANDOFF_IPTV_PVR_EPG_2026-11-20.md`. He confirmado que Tvheadend funciona correctamente: una red `IPTV LOCAL` con M3U `/storage/.user/playlist.m3u` que actualiza cada 60 min, respetando canales y orden. **La incidencia real es Kodi: añade nuevos pero conserva obsoletos en TVxx.db.** La limpieza compensatoria del addon es necesaria: no la elimines sin reemplazo probado. Audita API pvr.hts/TVH y esquema real Kodi en modo read-only; prepara tests, un plan de reconciliación fiable y rollback. CUID es ID permanente en IPTV Studio, pero no supongas que Kodi o TVH lo guardan. No editar producción, ni publicar M3U/ZIP ni reiniciar servicios sin autorización. El código va a `develop` con CI, tras gates PR hacia `main`; lo publicaré yo.
