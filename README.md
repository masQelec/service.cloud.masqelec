# Cloud masQelec — mantenimiento automático de KodiELEC

**Addon:** `service.cloud.masqelec` · **Versión:** 2.3.2 · **Kodi:** Python 3 · **Roles:** MASTER y CLIENT.

Este servicio mantiene los **montajes de medios**, la **base de datos de películas/series**, el **catálogo STRM**, **Tvheadend/PVR**, la **guía EPG** y la **actualización del sistema**. Se inicia con Kodi y repite tareas según su configuración. No es un reproductor multimedia: los archivos `.strm` apuntan a los archivos reales de OneDrive mediante los montajes rclone.

Esta descripción corresponde al **código validado en MASTER a 27/11/2026**, no a una propuesta. Los ensayos históricos y los detalles de implementación se mantienen en [docs/](service.cloud.masqelec/docs/README.md).

## 1. Qué hace al arrancar

`service.py::run_service()` ejecuta las operaciones **en este orden**. Los *one-shots* se ejecutan secuencialmente, no a la vez; si falla una tarea, el servicio registra el error y continúa con las siguientes.

| Orden | Función / módulo | Actuación real |
| --- | --- | --- |
| 1 | `cloud_storage.start_cloud_storage()` | Si está en modo v2 activo, **no descarga ni reinstala** los rclone/systemd legacy. En modos antiguos puede actualizar su configuración y unidades. |
| 2 | `rclone_two_mount_autostart.tick()` | Verifica el estado 2 FUSE + 4 bind, repara montajes v2 cuando procede y completa la retirada legacy. Tras confirmar v2, elimina OneDrive duplicado de `rclone.conf`. |
| 3 | `fix_settings.fix_skin_home_menu_visibility_and_reload()` | Desactiva determinados ajustes de menú del skin; recarga el skin solo si hubo cambios y está inactivo. |
| 4 | `updater.update_system()` | Si `auto_update` está activado y Kodi lleva al menos 300 s inactivo, compara `VERSION_ID` local/remota y prepara una actualización si existe. |
| 5 | `update_library.update_library()` | Si está permitido al arranque, valida `MyVideos*.db` y sus rutas/scrapers. Solo descarga y sustituye la base de datos si falta o no cumple; puede reiniciar Kodi tras la reparación. |
| 6 | `update_pvr.update_pvr()` | Coordinador PVR: recuperación pendiente, credenciales, playlist, ajustes XMLTV, actualizador Tvheadend, configuración y salud. |
| 7 | `_startup_maintenance_wrapper()` | Con red y montajes disponibles: sincroniza catálogo CLIENT, limpia cuando corresponde y genera/publica catálogo MASTER. Sin Scan de arranque. |
| 8 | Diagnóstico | Registra estadísticas de biblioteca, addons instalados relevantes y trata de subir el log al remoto `log:`. |

**Diferencia importante:** `update_library()` **no equivale** a `VideoLibrary.Scan`. La primera verifica/repara `MyVideos*.db`; el segundo escanea fuentes para actualizar el inventario de vídeo en Kodi.

En la fase 7 se comprueba red y estructura de montajes antes de sincronizar o limpiar. Las fases 4, 5 y 6 tienen **sus propias condiciones** y no heredan automáticamente esa barrera.

## 2. Mantenimientos periódicos

Tras el arranque se crean seis workers. Su *tick* de planificación es de 60 segundos salvo el trabajador OAuth adicional, programado cada hora.

| Mantenimiento | Cadencia por defecto | Condiciones y resultado |
| --- | --- | --- |
| Mantenimiento PVR integral | 12 h | Mismo coordinador que al arrancar; bloqueo, cooldown y resultado explícito. |
| Escaneo/sync biblioteca | 6 h | Ajustes activos, red, Kodi inactivo, montajes correctos y lock libre. MASTER escanea y después regenera/publica STRM. CLIENT sincroniza catálogo y solo escanea si hay cambios o desajuste DB↔FS. |
| Limpieza biblioteca | 12 h | Misma barrera de red/inactividad/montajes y lock. MASTER invoca `VideoLibrary.Clean`; CLIENT limpia según actualizaciones o entradas sobrantes y puede realizar un escaneo posterior. |
| Control montajes v2 | 60 s | Examina estado de migración y salud del árbol 2 FUSE + 4 bind; aplica mantenimiento/reparación autorizada, sin recrear cuatro FUSE legacy. |
| OAuth MASTER/CLIENT | 3600 s | Solo si el rol, estado v2 y flags permiten la operación. MASTER verifica/publica MQC2; CLIENT comprueba autorización OAuth y plantea recuperación por cuenta. |
| `rclone_token_sync.tick()` | 60 s | **Actualmente no opera** con `RCLONE_TOKEN_SYNC_ENABLED=False`. Es la ruta de sincronización heredada/alternativa, no un segundo recuperador activo. |

`0` horas en los intervalos configurables desactiva esa periodicidad. Los tiempos son aproximados: el worker despierta cada minuto y pospone tareas si faltan condiciones; no es un cron rígido. Los contadores de PVR, escaneo y limpieza se reinician con el proceso.

El mantenimiento PVR distingue intentos, éxitos y aplazamientos con su propio cooldown. Escaneo y limpieza disponen de sus protecciones específicas; `cloud_storage`, catálogo y updater también cuentan con protecciones propias. Estas barreras no equivalen a supervisión externa del resultado.

## 3. Biblioteca de vídeo y catálogo STRM

### MASTER

`lib/core_catalog.py::generate_catalog()` consulta las películas y episodios existentes en la biblioteca Kodi, genera `.strm` en un **staging**, calcula hash/versión y verifica el contenido antes de aplicarlo a las rutas locales `/storage/videos/` y `/storage/tvshows/`.

- El nuevo catálogo no se aplica mientras se está generando. La fase de aplicación dispone de respaldo persistente para rollback.
- Si el catálogo queda vacío o es inválido se bloquea; no se interpreta como una orden para borrar toda la biblioteca.
- Cuando cambia, genera `/storage/.catalog/catalog.zip` y `catalog.version`. `catalog_utils.load_catalog_github()` valida ZIP y manifiesto, publica **ZIP primero, versión después**. Si falla, conserva ZIP para el próximo intento; si no hay cambios, no vuelve a subirlo.
- Las rutas multimedia de los STRM remiten a los montajes v2 existentes. El proceso no mueve el contenido de OneDrive.

### CLIENT

`sync_catalog_https()` compara `catalog.version` con la versión local, descarga `catalog.zip` cuando procede, valida los miembros y aplica altas/cambios y eliminaciones bajo las comprobaciones de seguridad del catálogo.

- Después contrasta la existencia de los STRM locales con las entradas de la base de datos Kodi.
- Si hay elementos nuevos o faltantes: puede iniciar `VideoLibrary.Scan`.
- Si hay entradas sobrantes: puede iniciar `VideoLibrary.Clean` y, según la ruta de mantenimiento, un escaneo posterior.
- Si no hubo cambios y DB↔FS coincide, omite operaciones innecesarias.

**La biblioteca STRM se almacena internamente.** Una interrupción del FUSE puede impedir reproducir un vídeo, pero no implica borrar los STRM. Para evitar que un FUSE ausente se interprete como material eliminado, las tareas periódicas exigen que se mantenga la estructura de montajes y que Kodi no esté reproduciendo.

## 4. PVR, IPTV y guía EPG

MASTER y CLIENT utilizan el mismo coordinador PVR
y su propio Tvheadend local.

El arranque y el mantenimiento periódico comparten
`lib/update_pvr.py`.

Orden de ejecución:

1. Recuperación de transacciones pendientes.
2. Credenciales privadas.
3. Playlist M3U validada y escrita atómicamente.
4. Ajustes nativos XMLTV.
5. Actualización transaccional Tvheadend.
6. Configuración nativa del servidor.
7. Salud final.

La distribución utiliza la rama correspondiente a la
versión mayor de Kodi: rama `21` para Kodi 21.

La plantilla `pvr/playlist.m3u` conserva el orden y
los identificadores CUID. Las credenciales proceden
de `/storage/.user/user`.

No se emplea una reconciliación directa de la base de
datos PVR como mantenimiento ordinario ni se fuerza
un reinicio del stack por cada cambio de playlist.

Antes de actualizar Tvheadend se verifica convergencia
de URL entre la playlist y los mux existentes.

El actualizador comprueba plataforma, build, versión,
tamaño, SHA256, ELF y actividad antes de instalar.

Si no existe un manifiesto publicado, devuelve
`NO_RELEASE` y el mantenimiento continúa.

La reproducción, las grabaciones y determinadas
actividades de fondo aplazan las instalaciones reales.

La actualización dispone de backup, intercambio
atómico, verificación de salud, rollback, diario
persistente y recuperación previa al arranque de Kodi.

El nuevo grabber XMLTV se distribuye dentro del
paquete Tvheadend, no mediante sustitución independiente.

Guía EPG RAW:
https://raw.githubusercontent.com/masQelec/epg/main/guide.xml

La prueba física de altas, bajas y reapariciones de
canales sigue siendo un requisito independiente.

Documentación vigente:
[Handoff PVR final](service.cloud.masqelec/docs/HANDOFF_PVR_FINAL_2026-11-27.md).

## 5. Actualización del sistema KodiELEC

`lib/updater.py::update_system()` obtiene `VERSION_ID` y `COREELEC_DEVICE` desde `/etc/os-release`, consulta `masqelec:masqelec/update/<DEVICE>/os-release` y compara versiones numéricas.

Solo si la remota es **superior** descarga el paquete a staging y lo coloca en `/storage/.update`. Presenta al usuario la opción de reiniciar para actualizar o posponer al siguiente reinicio. No instala una versión inferior por ese flujo. La comprobación automática de arranque requiere `auto_update=true` y 300 segundos de inactividad.

Esta función actualiza **el sistema**; las versiones del addon se distribuyen separadamente mediante el repositorio de addons de Kodi.

## 6. Almacenamiento rclone y recuperación

Arquitectura activa, validada en MASTER y CLIENT piloto:

| Proceso | Montaje raíz | Bind de series | Bind de películas |
| --- | --- | --- | --- |
| OneDrive 1 | `/storage/.mnt/cloud/1` | `/storage/.mnt/tvshows/1` | `/storage/.mnt/videos/1` |
| OneDrive 2 | `/storage/.mnt/cloud/2` | `/storage/.mnt/tvshows/2` | `/storage/.mnt/videos/2` |

Solo hay **dos FUSE**; los cuatro bind reutilizan los mismos dispositivos de montaje del kernel. `rclone.conf` mantiene las dos conexiones Google Drive y remotos generales. OneDrive 1 y 2 usan respectivamente `/storage/.config/rclone/isolated-mounts/account1.conf` y `account2.conf`; cada uno contiene su `crypt` y credencial OAuth, con permisos privados.

El proceso de mantenimiento comprueba la topología en `/proc/self/mountinfo` **sin listar OneDrive**. Que un FUSE figure montado acredita su presencia en el kernel, **no** que Microsoft o la red respondan correctamente.

**OAuth v2:** MASTER reconstruye en memoria un canónico a partir de las configuraciones aisladas y la general; publica un MQC2 cifrado en `rclone/rclone-v2.conf.crypt` tras comprobaciones. CLIENT recupera únicamente la cuenta afectada ante un fallo AUTH identificado, verificando configuración, candidato, estado de reproducción y transacción de rollback. Los archivos STRM y la otra cuenta no forman parte de esa sustitución.

El ejecutor systemd de recuperación temprana intenta resolver transacciones interrumpidas antes del arranque completo de Kodi. Si hay un journal inconsistente debe bloquear acciones peligrosas y exigir revisión.

**Limitación conocida:** el comportamiento de OAuth ante una revocación real no se ha validado físicamente. Las sondas rclone pueden renovar tokens sobre copias temporales: se implementó una protección contra publicación de generaciones anteriores, pero sigue pendiente coordinar esa renovación con el escritor FUSE. Véase [incidencia OAuth #2](https://github.com/masQelec/service.cloud.masqelec/issues/2).

## 7. Ajustes disponibles en Kodi

En `resources/settings.xml`:

| Ajuste | Valor inicial | Efecto |
| --- | --- | --- |
| `auto_update` | Sí | Comprobar actualización del sistema al arrancar |
| `update_library` | Sí | Permiso general para mantenimiento de biblioteca |
| `lib_update_on_start` | Sí | Verificar/reparar MyVideos al iniciar |
| `lib_update_period_hours` | 6 | Intervalo de escaneo y sincronización de catálogo |
| `lib_clean_enabled` | Sí | Permitir CleanLibrary |
| `lib_clean_period_hours` | 12 | Intervalo de limpieza |
| `update_pvr` | Sí | Permitir mantenimiento PVR integral al arrancar |
| `pvr_update_enabled` | Sí | Permitir mantenimiento PVR periódico |
| `pvr_update_period_hours` | 12 | Intervalo de mantenimiento PVR |
| `pvr_disable_conflicts` / `pvr_disable_conflict_services` | Sí | Preferencias de conflictos PVR; verificar su aplicación antes de asumir que actúan siempre |
| `activar_log` / `ver_log` | Sí / acción | Archivo de registro y consulta desde Kodi |

Los flags internos de migración y OAuth viven en `lib/constants.py`; **no** son ajustes normales para cambiar desde la interfaz. Las rutas operativas de distribución utilizan la rama numérica correspondiente a Kodi.

## 8. Diagnóstico y operación

Para revisar los seis montajes sin acceder a contenidos ni credenciales:

```sh
grep -E ' /storage/\.mnt/(cloud|tvshows|videos)/[12] ' /proc/self/mountinfo
systemctl is-active \
  rclone_library_1.service rclone_library_2.service \
  masqelec_bind_tvshows_1.service masqelec_bind_tvshows_2.service \
  masqelec_bind_videos_1.service masqelec_bind_videos_2.service
```

El log del addon reside en el perfil Kodi de `service.cloud.masqelec` (archivo `service.log`). En el arranque se sobrescribe al primer registro; el addon intenta subirlo al remoto `log:` al finalizar los one-shots. No compartir tokens, ficheros `rclone.conf`, `account*.conf`, ficheros `/storage/.user/user` o logs completos sin revisar los datos privados.

Para ejecutar la regresión en Ubuntu:

```sh
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q
```

CI: [GitHub Actions](https://github.com/masQelec/service.cloud.masqelec/actions). El resultado de laboratorio no reemplaza una prueba física de reproducción, PVR o recuperación OAuth.

## 9. Estado y limitaciones

Validación confirmada el 27/11/2026:

- 1748 pruebas unitarias y de laboratorio.
- MASTER con Cloud 2.3.2 completo, 176 archivos.
- Persistencia tras reinicio y mantenimiento PVR OK.
- 714 canales, 54 grupos y 1428 asociaciones conservados.
- 2 FUSE, 4 bind y ninguna unidad legacy activa.
- Actualización CLIENTE aplazada durante reproducción.

Pendientes y límites:

- Revocación OAuth real y recuperación física.
- Actualización Tvheadend legacy en CLIENTE.
- Nuevo grabber nativo en funcionamiento real.
- Validación física NE y actualización nativa Cloud.
- Descarga del release definitivo desde GitHub.
- Altas, bajas y reapariciones de canales con control
  de huérfanos, identidad y orden.
- Convergencia de URL no equivale a verificar metadatos.
- Un montaje presente no acredita lectura remota sana.
- Las operaciones Scan/Clean conservan sus limitaciones
  de confirmación y timeout descritas en la auditoría.
- El resultado de rollback simulado no acredita
  recuperación frente a cualquier corte físico.

Los paquetes no se publican automáticamente por
consolidar el código en develop.

## Documentación técnica e historial

- [Arquitectura y roles](service.cloud.masqelec/docs/ARCHITECTURE_AND_MODES.md)
- [Operaciones y pruebas](service.cloud.masqelec/docs/OPERATIONS_AND_TESTING.md)
- [Auditoría post-main](service.cloud.masqelec/docs/AUDIT_POST_MAIN_2026-11-20.md)
- [Documentación completa y archivo histórico](service.cloud.masqelec/docs/README.md)
