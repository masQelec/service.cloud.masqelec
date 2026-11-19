> **Decisión aprobada por operador (19/11/2026):** mantener userdata para ajustes, logs y estado ordinario; usar `/storage/.config/masqelec/` para journal, respaldos y estado crítico de montajes. Ruta aceptada, despliegue de cutover todavía NO autorizado.

# Auditoría: userdata real del addon y ubicación del journal (19/11/2026)

## Evidencia: ZIP entregado por el operador

Archivo compartido: exportación de `service.cloud.masqelec/` del userdata actual del MASTER.
Inspeccionado como ZIP sin ejecutar ni extraer contenido. Cuatro archivos:
- `settings.xml` — ajustes Kodi (auto_update, update_library, update_pvr, limpieza, log).
- `state.json` — claves principales `circuit_breaker` y `cb`, métricas/estado del addon.
- `tvh_auth.json` — campos `user` y `pass`; **SECRETO: nunca copiar al repositorio**.
- `service.log` — registros de MASTER/Kodi 21.2, también identificadores de red y MAC; **NO copiar a GitHub**.

ZIP codifica modo `0644` para los cuatro ficheros; esto **no certifica** permisos en disco del MASTER. En concreto revisar seguridad de `tvh_auth.json` in situ, sin mostrar su contenido.

No había archivos de journal de transición, directorio `rclone-v2-transaction` ni snapshots OAuth dentro de este export. No permite concluir si existen en otras rutas del MASTER.

## Código actual y ubicación del userdata

- `lib/log_utils.py`: `xbmcvfs.translatePath(_addon.getAddonInfo("profile"))` y `service.log`.
- `lib/reliability_utils.py`: `special://profile/addon_data/service.cloud.masqelec`, `state.json`.
- `lib/update_pvr.py`: `/storage/.kodi/userdata/addon_data/service.cloud.masqelec/tvh_auth.json`.

Ruta física probable en CoreELEC:
`/storage/.kodi/userdata/addon_data/service.cloud.masqelec/`.
Verificar ubicación efectiva con Kodi/SSH; `special://profile` depende del perfil seleccionado.

## Decisión arquitectónica pendiente: datos de recuperación del motor

**Opción A: `/storage/.config/masqelec/` (recomendada para journal y recuperación).**
Pros: ajeno a operaciones de *restablecer ajustes/desinstalar addon*, ruta absoluta y disponible
en boot de systemd antes de Kodi; sin mezcla con logs/ajustes o manejo por API de Kodi.
Requisitos: inicialización segura en primera migración, dueño root, modo 0700 para contenedores
privados, fsync del directorio; impedir borrado al reiniciar. El código aún presupone
incorrectamente la existencia de este directorio en el preflight; corregir.

**Opción B: subdirectorio aislado de userdata, p.ej.**
`/storage/.kodi/userdata/addon_data/service.cloud.masqelec/recovery/`.
Pros: mismo espacio de datos por addon, ruta ya establecida en el MASTER.
Riesgos: susceptible a borrado de datos/desinstalación/restauración de perfil; debe
ser un subdirectorio propio de root 0700, no el directorio base que contiene log y
settings. No usar API Kodi ni ruta `special://profile` dinámica para journal de
systemd, que necesita una ruta física absoluta estable incluso cuando Kodi no está
iniciado. Un directorio 0700 dentro de userdata no debe bloquear las escrituras
habituales del addon a settings, log o state. La recuperación debe funcionar sin Kodi.

**No guardar secretos OAuth en `state.json`, `settings.xml` ni `service.log`.**
No sustituir la config original `/storage/.config/rclone/rclone.conf` por un fichero
userdata. Los archivos privados aislados `account1.conf` y `account2.conf` son
configuraciones operativas de los procesos rclone: hoy el plan los coloca bajo
`/storage/.config/rclone/isolated-mounts/`.

### Recomendación provisional

Mantener **userdata** para los ajustes, estado no crítico, autenticación de TVH (con
permisos corregidos), logs y preferencias. Reservar `/storage/.config/masqelec/`
para journal de recuperación y marcador de arquitectura cuyo ciclo de vida debe
sobrevivir a Kodi, actualizaciones y posible eliminación de datos del addon.

Ubicación elegida por el operador. Persisten las verificaciones de permisos y directorios del MASTER antes del cutover. No alterar montajes todavía.

## Estado

```text
AUDIT_USERDATA_ZIP=COMPLETE
OAUTH_SECRETS_EXPOSED_IN_REPORT=NO
RECOVERY_STORAGE_LOCATION=/storage/.config/masqelec
CUTOVER_AUTHORIZED=NO
```
