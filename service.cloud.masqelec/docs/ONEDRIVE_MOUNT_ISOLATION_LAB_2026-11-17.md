# Rclone OneDrive — aislamiento por proceso (fase laboratorio)

Fecha: 2026-11-17. Rama: addon `develop`. No se ha modificado `main`
ni `cloud.masqelec/develop` ni las unidades systemd operativas.

## Evidencia

La suite anterior pasó 123/123 (informado por operador).
El laboratorio real devolvió LIVE_CONFIG_MOUNTS_ACTIVE=YES,
ISOLATED_CONFIG_MOUNTS_ACTIVE=NO, LAB_RESULT=PASS.

En `cloud.masqelec/develop/system.d` existen cuatro unidades:
rclone_tvshows_1, rclone_tvshows_2, rclone_videos_1 y rclone_videos_2.
Los servicios 1 y 2 de películas y series repiten las mismas dos cuentas
OneDrive (`users_library_1` y `users_library_2`). Todos usan
`/storage/.config/rclone/rclone.conf`, lo que permite escrituras
concurrentes de refresh tokens. Rclone exige config escribible y guarda
renovaciones mediante rename; no hay CAS entre procesos.

## Propuesta aislada (NO desplegada)

`lib/rclone_mount_isolation.py` genera en /tmp propuestas para cuatro
configuraciones independientes. Cada fichero contiene únicamente el remoto
OneDrive necesario. Los cuatro borradores de unidades cambian solo
`--config` a rutas distintas bajo
`/storage/.config/rclone/isolated-mounts/<service>.conf`.

El módulo no llama a systemctl, no interrumpe montajes y no edita el
`rclone.conf` real ni los datos publicados en GitHub.

**Riesgo residual:** dos procesos distintos pueden generar refresh tokens
diferentes para la misma cuenta. Tener cuatro archivos elimina colisiones
de escritura del fichero compartido, **pero no sincroniza las credenciales**.
No se permite elegir un token por mtime ni suponer que el último access
token indica el refresh más nuevo. `account_divergence()` solo distingue
`consistent` y `diverged`, y rechaza cambios de identidad.

Para recuperarse en ejecución se necesita un coordinador de credenciales,
validar el token elegido y una política explícita de aplicación de cambios
en los procesos ya iniciados. Rclone no ofrece aquí una garantía verificada
de recargar OAuth en una instancia mount existente.

La ruta de despliegue, cuando esté ensayada, deberá evitar los
`try-restart` que actualmente puede ejecutar
`lib/cloud_storage.py` al actualizar unidades durante el arranque.
No modificar las cuatro unidades en cloud/develop todavía.

## Gates

- `RCLONE_TOKEN_SYNC_ENABLED = False` hasta laboratorio real completo.
- Las nuevas 12 pruebas son unitarias y no utilizan servicios activos.
- El ensayo en KodiELEC debe usar directorio temporal 0700, ficheros 0600,
  sin reiniciar servicios ni ejecutar OAuth automáticamente.
- No confundir un laboratorio PASS con recuperación transparente real.

## Laboratorio real de aislamiento, sin migrar

El script `tools/rclone_mount_isolation_lab.py` crea 8 archivos
temporales y privados: 4 configs con un único OneDrive y 4 propuestas de
unidades. Importa los módulos desde el commit inmutable
`adbd506fa0a1a9237b81d19a379fd5bd1e41939a` y descarga en modo
solo lectura las unidades actuales de `cloud.masqelec/develop`.

    wget -q https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/develop/service.cloud.masqelec/tools/rclone_mount_isolation_lab.py -O /tmp/rclone_mount_isolation_lab.py
    python3 -m py_compile /tmp/rclone_mount_isolation_lab.py
    python3 /tmp/rclone_mount_isolation_lab.py

El ensayo no consulta OAuth, no escribe en el directorio de rclone y
elimina automáticamente las copias privadas al finalizar. Verificar
`UNITS_MATCH_DEVELOP=PASS`, `ISOLATED_CONFIG_FILES=4`,
`GENERATED_UNIT_PROPOSALS=4`, `ONEDRIVE_ACCOUNTS=2`,
`ACCOUNT_TOKENS_CONSISTENT=2`, `STAGED_FILES_MODE_0600=PASS` y
`LAB_RESULT=PASS`. La prueba no confirma la adopción de nuevos tokens
por montajes actualmente activos.
