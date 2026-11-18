# Primer arranque automático de Kodi: transición y retirada de unidades legacy

**Revisión: 19/11/2026. Código en `develop`; no publicado, no activado ni probado con OneDrive real.**

## Decisión de producto

El operador publica el ZIP y mantiene el repositorio de actualizaciones Kodi. Cada equipo MASTER o CLIENTE recibe el addon actualizado a su propio ritmo y **el primer arranque del nuevo addon** debe migrar sus montajes de 4 procesos rclone FUSE a 2 FUSE + 4 bind. Ningún equipo tiene ambos esquemas activos a la vez. No hay migración manual dispositivo a dispositivo ni interrupción de toda la flota.

Las rutas antiguas **no cambian**:
`/storage/.mnt/tvshows/1`, `/storage/.mnt/tvshows/2`, `/storage/.mnt/videos/1`, `/storage/.mnt/videos/2`. Los `.strm` siguen en el almacenamiento local y no se reconstruyen. Si Kodi reproduce, hay riesgo de corte de vídeo al desmontar, y la caché no garantiza continuidad; el addon **difiere la transición** hasta `Player.GetActivePlayers == []`.

## Implementación añadida

| Archivo | Responsabilidad | Gate |
| --- | --- | --- |
| `lib/rclone_two_mount_autostart.py` | Evalúa modo local; arranca una transición o limpieza idempotente; difiere con reproducción; recupera solo tras autorización explícita | FIRST_RUN/FEATURE/ROLLBACK y otros |
| `service.py` | Llama una vez tras `cloud_storage` y añade `periodic_rclone_v2_cutover` cada 60 segundos | `tick` regresa `DISABLED` por defecto |
| `lib/rclone_two_mount_live_adapter.py` | Preflight, snapshot, exclusión y transición; verifica seis montajes y dos lecturas conocidas; ahora distingue `disabled` exacto del fallo en `systemctl is-enabled` | `live_enabled` + autorización externa |
| `lib/rclone_two_mount_legacy_cleanup.py` | Elimina **exclusivamente** cuatro archivos `.service` originales tras `ACTIVE` y copia journal comprobada, nunca OAuth/STRM; reinicia limpieza después de corte | LEGACY_RETIRE_ENABLED, journal ACTIVE y salud |
| `lib/rclone_two_mount_boot_guard.py` | Bloquea tareas legacy ante journal interrumpido o marcador inconsistente | Solo lectura |

**Orden de primera ejecución en el mismo dispositivo:**

1. `cloud_storage.py` puede actualizar las unidades legacy **mientras siga en modo legacy**, nunca si `active` o `unsafe`.
2. `autostart.tick` exige root, dos archivos de vídeo **conocidos** (uno por cuenta en las rutas oficiales), identidad/rollback habilitados, respuesta Kodi JSON-RPC válida y ausencia de reproducción.
3. `live_adapter.execute_with_local_lock` toma flock local, lee el canonical privado, verifica exactamente cuatro legacy FUSE y unidades sanas, guarda journal durable 0600, escribe marcador unsafe, **deshabilita legacy antes de detenerlo**.
4. Después de confirmar cero legacy montados instala los dos `account*.conf` privados y las seis unidades candidatas. Inicia dos FUSE, cuatro bind, confirma `mountinfo` y lectura de 1 byte de un vídeo conocido por cada cuenta.
5. Marca `ACTIVE` después de la verificación. Deshabilita legacy y habilita seis servicios v2 (los inicios reales se prueban después).
6. El limpiador toma **otro bloqueo local** y confirma journal `active`, cuatro respaldos legacy originales, montaje v2 sano, legacy no activos y estado `systemctl is-enabled` inequívoco: `disabled` para archivos presentes o `disabled/not-found` exacto para los ya retirados. No trata un fallo general de systemctl como unidad deshabilitada.
7. Solo entonces retira las cuatro unidades legacy originales si son **byte a byte idénticas** a su snapshot. Conserva los respaldos privados y el estado activo. Ejecuta `daemon-reload` y escribe `legacy-unit-cleanup.done` durable.
8. Si se corta alimentación entre la retirada de dos archivos, etc., el siguiente tick entra en `ACTIVE` y reintenta **solo** la limpieza faltante. Si encuentra archivo cambiado, symlink, drop-ins legacy o resultados ambiguos, **no borra más**. Nunca recrea legacy en un dispositivo ACTIVE.
9. Si falla el cutover antes de ACTIVE, el motor intenta rollback de binds, FUSE, tokens y unidades antiguas; ante fase insegura o reboot sin recuperación verificada, el boot guard bloquea tareas. No se asume restauración automática probada en KodiELEC hasta validar el protocolo de recuperación física.

**Nota de implementación:** la activación no es una orden `rm`. El borrado ocurre tras comprobaciones de exactitud, y los respaldos sobreviven para recuperación. Los `.strm` no se abren para escrituras.

## Los cinco gates adicionales de release (todos cerrados)

```text
RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED=False
RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED=False
RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED=False
RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES=()
```

También se mantienen `RCLONE_TWO_MOUNT_STAGING_ENABLED=False`, `RCLONE_TOKEN_SYNC_ENABLED=False` y `RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED=False`.

**Resultado real:** el laboratorio de **systemd LOCAL** pasó 2 FUSE + 4 bind y limpieza. El cutover de las unidades definitivas reales y la reproducción Kodi en OneDrive **NO han pasado**. No activar estas banderas en este punto.

**Bloqueador funcional para el despliegue a todos los dispositivos:** todavía no existe una selección automática/verificada de **un fichero multimedia de prueba por cuenta** desde el catálogo local; la constante `RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES` está vacía. El diseño actual *fallaría cerrado* con `BLOCKED_MEDIA_FIXTURES` si se activase sin resolver esto. No publicar una release con el cambio automático antes de solucionar esta selección y las pruebas reales.

## Inventario de pruebas y riesgos

- Pruebas sintéticas de primer arranque: 21 tests de estados/flags, playback activo, defer, idempotencia, rollback y conexión al servicio.
- Pruebas sintéticas de limpieza post-ACTIVE: 22 tests para ficheros alterados, symlinks, permisos, backup privado, reinicio parcial, `daemon-reload` fallido y estado ambiguo systemd.
- `systemctl is-enabled --quiet` no es un indicador seguro de `disabled`: diferencia salida `disabled`, `not-found` (rc4), `enabled`, `masked`, errores e indisponibilidad; nunca borra ante desconocido.
- CI [44424953101](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44424953101) **754/754 PASS**. Sin red, sin Kodi ni OAuth reales.
- **Pendiente:** prueba física de upgrade en Kodi con versión instalable, lectura OAuth de las dos cuentas, reinicio en distintos puntos del corte, limpieza systemd real, pruebas de downgrade y restauración de unidades del journal; el user publicará ZIP únicamente cuando gates estén satisfechos.
- **Pendiente:** recuperación CLIENTE v2 desde `rclone-v2.conf.crypt`; publicación MASTER v2 preparada con flags desactivados. El fichero remoto v2 aún no existe.

## Handoff

Siguiente objetivo técnico: **resolver la obtención segura de archivos conocidos en las carpetas STRM locales de cada KodiELEC** para que la migración sea realmente autónoma en todos los equipos, y montar un laboratorio de upgrade/reboot real con archivos de media inocuos. Luego verificar limpieza de cuatro unit files de producción y recuperación en caso de fallo. No ejecutar cutover productivo todavía.
