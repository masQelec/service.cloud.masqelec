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

## Diagnóstico del ensayo en KodiELEC

El operador obtuvo `UNITS_MATCH_DEVELOP=PASS`, seguido de
`LAB_RESULT=ERROR_ValueError`. El fallo sucede **después** de
validar las cuatro unidades, pero la versión anterior del script no
indicaba la operación exacta. No hay evidencia de que se haya
modificado la configuración activa.

La validación inicial de `stage_in_directory()` usaba
`os.path.realpath(root).startswith("/tmp/")`, demasiado rígida cuando
`/tmp` resuelve a otro tmpfs mediante symlink (posible en KodiELEC).
Se sustituye por `os.path.commonpath((realpath(root), realpath("/tmp")))`
y se exige un directorio hijo, manteniendo el bloqueo de rutas fuera del
temporal. Dos pruebas comprueban tanto el caso permitido como el intento
de salir del directorio temporal.

El laboratorio actualizado informa `TEMP_REALPATH_SAFE=YES/NO`,
`UNIT_N_REMOTE_PROVIDER` (ONEDRIVE/DRIVE/MISSING/OTHER),
`UNIT_N_PREPARED` y `LAB_FAILED_AT`, sin revelar los nombres de remotos,
rutas de secretos ni valores de tokens.

**La causa exacta no se considera confirmada** hasta ejecutar la nueva
versión y observar el diagnóstico. Total esperado: 137 pruebas
(123 verificadas + 12 de aislamiento + 2 de ruta temporal).

## Resultado real: el nombre montado es un remoto virtual (2026-11-17)

El operador completó las 137 pruebas: `Ran 137 tests ... OK`.
El laboratorio en KodiELEC devolvió `UNITS_MATCH_DEVELOP=PASS`,
`TEMP_REALPATH_SAFE=YES`,
`UNIT_1_REMOTE_PROVIDER=OTHER`,
`LAB_FAILED_AT=SELECT_REMOTE_1`. La ruta temporal era correcta.
El error real estaba en asumir que `users_library_1` era directamente
`type=onedrive`, sin resolver sus dependencias.

La implementación `dependency_closure` admite raíces OAuth directas y
backends virtuales alias/crypt/chunker (clave `remote`) y union/combine
(clave `upstreams`). Sigue referencias nominales de forma recursiva,
conserva los parámetros de las secciones necesarias y rechaza ciclos,
referencias ausentes, rutas locales, conexiones inline y backends no
reconocidos. El aislamiento mantiene las cuatro OAuth o las que sean
realmente necesarias para cada raíz; **no** se puede asegurar todavía que
cada unidad solo necesite una cuenta OneDrive.

La reconciliación `account_divergence()` compara tokens por nombre del
remoto OAuth efectivo, no por el nombre del wrapper. Si dos montajes usan
una credencial común y sus refresh_token difieren, devuelve `diverged`
sin elegir ni publicar una versión. Nunca elimina secciones necesarias.

Los tipos y referencias exactos del dispositivo siguen siendo desconocidos
hasta ejecutar el laboratorio corregido. Se añadieron 12 pruebas con raíces
alias, crypt, chunker, union, combine, ciclos y dependencias ausentes.
El total previsto pasa de 137 a **149**.

## Aclaración del operador: `crypt` y nombres sin cifrar

El operador confirmó que utiliza `rclone crypt` para **cifrar los datos,
pero no los nombres de archivo**. La raíz usada por cada montaje es una
sección virtual `crypt` que referencia otra sección remota con la cuenta
de almacenamiento; los nombres exactos se respetan tal como consten en
`rclone.conf` (no se deducen ni renombran). El anterior laboratorio
falló en `UNIT_1_REMOTE_PROVIDER=OTHER` porque consideraba que la raíz
debía tener `type=onedrive`.

La selección segura conserva en el fichero por proceso:
- la sección `crypt` original COMPLETA, con sus valores de `remote`,
  `password`, `password2`, `filename_encryption`,
  `directory_name_encryption` y cualquier otra opción;
- la sección OAuth real de la que depende y sus opciones originales;
- cualquier otra sección referenciada recursivamente por wrappers
  admitidos, sin eliminar dependencias.

En particular se conserva `filename_encryption = off` cuando aparece:
NO se habilita el cifrado de nombres y NO se modifican rutas de medios.
El cifrado de datos continúa dependiendo de la configuración `crypt`
original. El plan no convierte, migra ni reescribe datos remotos.

Se añaden pruebas que comparan exactamente los ajustes de `crypt`,
verifican aislamiento entre las dos cuentas y bloquean dependencias
ausentes. Total previsto de pruebas tras este cambio: **152**.

## Laboratorio con la cadena `crypt -> OneDrive`

El laboratorio `tools/rclone_mount_isolation_lab.py` queda fijado al
commit `23ec52b3b8662b43d2c2e871ae8ef5dedc44fd86` para descargar el
nuevo generador. Para cada unidad muestra sin secretos:

- `UNIT_N_REMOTE_PROVIDER`: se espera `CRYPT`.
- `UNIT_N_CHAIN_SECTIONS`: se esperan normalmente 2 secciones
  (wrapper crypt y remoto OAuth), salvo dependencias adicionales.
- `UNIT_N_ONEDRIVE_DEPENDENCIES`: se espera 1 por unidad.
- `UNIT_N_OAUTH_DEPENDENCIES`: se espera 1 por unidad.
- `UNIT_N_FILENAME_ENCRYPTION`: se espera `OFF` según el operador.
- `UNIT_N_DATA_ENCRYPTION`: se espera `ON` según el operador.
- `LAB_RESULT=PASS` si se han generado los 4 planes independientes,
  comprobado la consistencia y preservado la configuración operativa.

No se han instalado las propuestas systemd, no se toca `rclone.conf`
real y la sincronización OAuth sigue desactivada. Sigue sin existir
una recuperación transparente de montajes en caliente.
