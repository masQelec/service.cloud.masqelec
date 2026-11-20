# Auditoría funcional del mantenimiento — 20/11/2026

**Base inspeccionada:** rama `main`, commit `4fa6c21eec9af22302a83214b44287cdd19557ef`, addon 2.3.2. La revisión sigue las llamadas de `service.py` a `cloud_storage`, `rclone_two_mount_autostart`, `updater`, `update_library`, `update_pvr`, `core_catalog`, `catalog_utils`, `fix_settings`, `rclone_token_sync` y los workers OAuth. Revisión estática; no se han ejecutado operaciones reales de PVR, Kodi, montaje o tokens.

## Comportamiento confirmado

El arranque tiene una fase bloqueante `start_cloud_storage`; luego `rclone_two_mount_autostart.tick`; después los one-shots secuenciales `fix_settings`, `auto_update`, `library_update`, `pvr_update`, `startup_maintenance`. Finalmente registra estadísticas de biblioteca, versiones de addons y sube `service.log`.

Los workers se crean **después** de todos los one-shots. Cada minuto se evalúan PVR, CleanLibrary, UpdateLibrary, mantenimiento de montajes y `rclone_token_sync.tick()`; cada hora se ejecuta el worker adicional OAuth v2. La configuración interna actual establece `RCLONE_TOKEN_SYNC_ENABLED=False`, por lo que el tick de sincronización anterior no realiza trabajo; el worker OAuth v2 adicional sí dispone de flags habilitados y verifica rol/estado.

El MASTER genera STRM desde la base Kodi en staging, aplica con resguardo para rollback y publica `catalog.zip` antes de `catalog.version`. El CLIENT descarga e instala la versión correspondiente, puede eliminar STRM obsoletos tras validación, y contrasta DB de Kodi con sistema de archivos para decidir Scan/Clean.

Los montajes v2 activos son 2 FUSE y cuatro bind. `cloud_storage.start_cloud_storage` abandona el flujo legacy cuando detecta modo `active`; `rclone_two_mount_autostart` comprueba estructura/estado y llama mantenimiento/retirada de legacy. `rclone.conf` general queda sin los dos OneDrive; `isolated-mounts/account{1,2}.conf` contienen crypt + OAuth por cuenta.

### Matriz de riesgos y recomendaciones

| Identificador | Severidad | Evidencia | Recomendación |
| --- | --- | --- | --- |
| M-01 | Alta | `_update_pvr_wrapper` ejecuta PVR al arranque sin comprobar reproducción; `_startup_maintenance_wrapper` ejecuta `update_playlist()` sin playback idle. Si cambia playlist, `update_playlist()` puede parar Tvheadend/deshabilitar `pvr.hts` y reconciliar canales. | Evitar reset disruptivo durante reproducción o grabación. Comprobar **grabaciones reales de TVH** además del player Kodi. |
| M-02 | Media | `_periodic_pvr_worker` ignora el primer booleano de `update_playlist()` y llama `_task_mark_success('pvr')` si no hubo excepción. | Propagar estados y programar reintentos ante `ok=False`. |
| M-03 | Media | `update_library_silent()` y `clean_library_silent()` devuelven `False` ante timeout o si no se observó inicio. Sus callers ignoran el resultado y registran marcas de última ejecución. | No informar éxito sin confirmación; distinguir no-op de timeout y error. |
| M-04 | Media | `_periodic_update_worker` / `_periodic_clean_worker` CLIENT retornan sin actualizar fecha cuando DB↔FS está al día. | Valorar temporizador separado para chequeo de catálogo frente a escaneo/limpieza, para evitar trabajo repetido por minuto. |
| M-05 | Media | `_mounts_ready()` valida 2 FUSE/4 bind leyendo `/proc/self/mountinfo` (sin listar OneDrive). | No interpretar estructura correcta como disponibilidad de medios o salud OAuth; usar sondas acotadas e independientes. |
| M-06 | Alta residual | Sondeos de rclone con copia temporal pueden generar OAuth de nueva generación y descartarla si el writer FUSE no interviene. | Seguimiento en [OAuth #2](https://github.com/masQelec/service.cloud.masqelec/issues/2); no revocar tokens reales todavía. |
| M-07 | Media | `constants.CLOUD_BRANCH='develop'` aun con addon en `main`. | Planificar canal de configuración estable separado, sin cambiar URLs por renombrado. |
| M-08 | Media | Existen ajustes `pvr_disable_conflicts` y `pvr_disable_conflict_services` en XML que no aparecen referenciados directamente en `update_pvr.py`; algunos flags en `constants.py` mantienen comentarios de laboratorio desfasados. | Verificar consumidores completos antes de retirar opciones; actualizar texto y pruebas cuando se precise. |

**No se declara que M-01/M-02/M-03 hayan provocado una pérdida de datos.** Son discrepancias entre el estado comunicado/planificación y la comprobación real. Seguimiento detallado: [Issue #4](https://github.com/masQelec/service.cloud.masqelec/issues/4).

## Decisiones de documentación

El README principal deja de ser un diario cronológico de 2026: ahora describe **funciones, orden, cadencias, precondiciones, efectos, rutas, parámetros y diagnóstico**. Se conserva el historial íntegro en `service.cloud.masqelec/docs/`. Las referencias a procedimientos de rollout de noviembre deben interpretarse como historia, no como instrucciones operativas vigentes.

## Gates de salida

- README tiene que concordar con `service.py`, `settings.xml`, `update_pvr.py`, `update_library.py` y `core_catalog.py`.
- Ningún cambio de código de mantenimiento en esta entrega; solo documentación e incidencia de seguimiento.
- GitHub Actions PASS para develop y PR/main antes de cerrar integración.
- No se ha publicado paquete ZIP, reiniciado dispositivos, ni modificado `cloud.masqelec`.
