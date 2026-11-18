# Piloto aislado de 2 FUSE + 4 bind — masQelec/KodiELEC

**Fecha:** 18-11-2026 · **Rama:** addon `develop` · **Versión inmóvil del script:** `17963e287152afe1cb845f73d460cdfd53b81091` · **Sin deploy**.

## Objetivo y límite

Validar en un dispositivo KodiELEC real que el binario rclone soporta montaje FUSE, que se pueden crear **dos FUSE y cuatro bind mounts** en rutas completamente alternativas a la biblioteca y que se desmontan limpiamente. Este ensayo usa exclusivamente el backend **local** con datos falsos, **no** los remotos OneDrive, wrappers `crypt` ni archivos `.strm`. Por tanto, ni un PASS real demuestra la reproducción de contenido desde OneDrive o la compatibilidad de `Type=notify` bajo systemd.

**La lógica MASTER/CLIENTE y el catálogo ya están implementados y no se modifican**: MASTER explora montajes, genera `.strm` y ZIP; CLIENTES importan el catálogo y escanean exclusivamente las carpetas de `.strm` locales; rclone se utiliza al reproducir por la ruta descrita en cada `.strm`.

El piloto es `tools/rclone_two_mount_fuse_bind_local_lab.py`: script **autocontenido**. No requiere desplegar la versión nueva del addon. No lee `rclone.conf`, ni MQC2, ni claves SSH; no ejecuta `rclone lsf`, OAuth, ninguna llamada a GitHub, `systemctl` ni modifica el servicio.

## Paso 1 — preflight sin montajes ni cambios de sistema

Consola SSH del dispositivo de laboratorio (no altera montajes, ni OneDrive ni la biblioteca):

```bash
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/17963e287152afe1cb845f73d460cdfd53b81091/service.cloud.masqelec/tools/rclone_two_mount_fuse_bind_local_lab.py' -O /tmp/rclone_two_mount_fuse_bind_local_lab.py
python3 -m py_compile /tmp/rclone_two_mount_fuse_bind_local_lab.py
python3 /tmp/rclone_two_mount_fuse_bind_local_lab.py --preflight
```

El resultado contiene solamente estados booleanos, nunca argumentos completos de rclone ni secretos. Comprueba la presencia del binario en `/storage/.config/rclone/rclone`, `/usr/bin/rclone` o PATH, y consulta **`rclone mount --help` localmente** para confirmar las opciones `--read-only`, `--vfs-cache-mode`, `--config`. Comprueba `mount`, `umount`, `/dev/fuse`, `mountinfo` y permisos de superusuario para bind. No prueba autenticación de la nube.

Éxito preliminar (todas las precondiciones presentes):

```text
LAB_MODE=RCLONE_TWO_FUSE_FOUR_BIND_LOCAL
ONEDRIVE_ACCESSED=NO
RCLONE_LIVE_CONFIG_READ=NO
KODI_PATHS_CHANGED=NO
SYSTEMD_WRITE=NO
GITHUB_UPLOAD=NO
RCLONE=YES
RCLONE_MOUNT_FLAGS=YES
FUSE_DEVICE=YES
MOUNT=YES
UMOUNT=YES
MOUNTINFO=YES
PRIVILEGED=YES
TYPE_NOTIFY_REAL_SYSTEMD=NOT_TESTED
LAB_RESULT=READY_FOR_LOCAL_PILOT
```

Si cualquier requisito falla, `BLOCKED_MISSING_LOCAL_PREREQUISITE`, exit code 2. **No modificar las unidades actuales para resolverlo**.

## Paso 2 — piloto local REAL opcional, con consentimiento expreso en la consola

Solo después de un preflight satisfactorio y desde el dispositivo donde se autorice el laboratorio:

```bash
python3 /tmp/rclone_two_mount_fuse_bind_local_lab.py --run-local-pilot --confirm-isolated-only
```

Este comando **sí realiza cambios temporales locales**: crea con `mkdtemp` una carpeta `/tmp/masqelec-fuse-local-*/` (0700), con dos fuentes locales ficticias, dos destinos FUSE y cuatro destinos bind. Lanza dos procesos `rclone mount` (backend local, `--config /dev/null`, `--read-only`), ejecuta cuatro `mount --bind` **solo dentro del temporal**, valida seis montajes mediante `mountinfo` y lee un fichero de prueba por cada bind. Siempre intenta desmontar los cuatro binds en orden inverso, desmontar los FUSE y terminar **solo** los procesos creados por el laboratorio.

- `LAB_RESULT=PASS_LOCAL_FUSE_BIND_LAB`: dos FUSE y cuatro bind + lecturas observadas. **No indica prueba sobre OneDrive/crypt, Type=notify ni Kodi**.
- `LAB_RESULT=FAIL_LOCAL_*`: no iniciar migración.
- `LAB_RESULT=FAIL_LOCAL_CLEANUP`: aunque la lectura y los montajes fueran correctos, **NO PASS** si quedó algún FUSE/bind temporal o falló su limpieza. El resultado de la prueba se considera fallido; revisar únicamente rutas de `/tmp/masqelec-fuse-local-*`.
- `CLEANUP=INCOMPLETE_TEMP_PATH_REQUIRES_MANUAL_REVIEW`: algún montaje temporal puede seguir montado. **No borrar a mano ni forzar desmontajes de rutas originales Kodi**; revisar `/proc/self/mountinfo` y actuar únicamente sobre rutas que empiecen por `/tmp/masqelec-fuse-local-`.
- `LAB_RESULT=BLOCKED_INVALID_MODE`: falta confirmación exacta o argumentos no admitidos; no inicia ningún montaje.

`/tmp` debe ser el directorio real, no un enlace simbólico. El modo de ejecución no acepta destinos personalizados ni parámetros que apunten a `/storage`.

## Qué se valida en CI y qué sigue pendiente

| Control | Evidencia | Resultado |
| --- | --- | --- |
| Comparación de 2 FUSE y 4 bind parametrizada por rutas alternativas | `lib/rclone_two_mount_health.py` | PASS sintético |
| Compatibilidad con semántica legacy de `ValueError` para mountinfo truncado | Regresión corregida | PASS |
| Rechazo de bind repetidos, cuenta equivocada, directorio incorrecto | Pruebas negativas | PASS |
| Preflight offline, selección del binario KodiELEC, argumentos seguros y limpieza | Tests de piloto aislado | PASS sintético |
| Suite completa Python 3.11 | GitHub Actions [44351743573](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44351743573): **406/406 OK** | **PASS CI** |
| Preflight en KodiELEC real | No se ha recibido salida del operador | **NOT RUN** |
| Dos FUSE y cuatro bind temporales reales | No se ha ejecutado en KodiELEC | **NOT RUN** |
| `Type=notify` para el binario exacto del dispositivo | No probado bajo systemd | **NOT RUN** |
| Montaje `users_library_1:` + `users_library_2:`, lectura crypt/OneDrive | Sin OAuth ni credenciales reales en el piloto | **NOT RUN** |
| Reproducción mediante `.strm` y rollback de rutas Kodi reales | No se han tocado | **NOT RUN** |

## Siguiente fase, solo tras el piloto real

Si los montajes locales temporales funcionan, estudiar compatibilidad de `Type=notify` y un ensayo de lectura **sin escanear directorios OneDrive** sobre rutas alternas, sin introducir una copia de tokens que pueda rotar o reescribir los originales. Después elaborar cutover y rollback por dispositivo. El MASTER y CLIENTES seguirán realizando exactamente sus funciones actuales; el cambio afecta únicamente a la capa de montaje.

## Flags y restricciones sin cambios

```text
RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TWO_MOUNT_STAGING_ENABLED=False
CUTOVER_EXECUTOR=NOT_IMPLEMENTED
LIVE_FUSE_BIND_MIGRATION=NOT_EXECUTED
CLOUD_SYSTEMD_CHANGED=NO
GITHUB_OAUTH_PUT=NO
```

### Corrección de cierre (18-11-2026)

Al auditar el flujo de salida se encontró que una versión inicial podía devolver PASS aunque la limpieza del laboratorio fallase. Corregido en commits `e4140dc8`, `bae1e203` y `c6c776c` con 2 pruebas adicionales, incluyendo fallo de limpieza después de una simulación completamente satisfactoria. **El script que debe descargarse es el referenciado por el SHA `17963e287152afe1cb845f73d460cdfd53b81091` de esta página**, no el original; GitHub Actions [44351743573](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44351743573): `Ran 401 tests ... OK`. Esto sigue sin equivaler a un FUSE real probado en KodiELEC.

## Resultado real KodiELEC del primer preflight y corrección (18-11-2026)

**Salida facilitada por el operador:** FUSE_DEVICE, MOUNT, MOUNTINFO, PRIVILEGED, RCLONE y UMOUNT `YES`; `RCLONE_MOUNT_FLAGS=NO` y `LAB_RESULT=BLOCKED_MISSING_LOCAL_PREREQUISITE`. **No hubo petición OAuth, montaje ni escritura operativa.** La causa exacta en ese binario aún requiere repetir el preflight.

**Error detectado en el laboratorio:** se exigía `--config` en la ayuda de `rclone mount`, cuando es una opción **global** y puede no listarse allí. Se ha separado la consulta: `rclone mount --help` comprueba `--read-only`/`--vfs-cache-mode`; `rclone help flags` (o `rclone --help` como alternativa) comprueba `--config`. Además se ha eliminado una referencia a `health.mount_entries` que no existía en el script standalone durante la espera de FUSE. **No se relaja ninguna condición de seguridad**: una opción realmente ausente sigue bloqueando.

**Código corregido, referencia inmutable**: `17963e287152afe1cb845f73d460cdfd53b81091`. CI del código [44351743573](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44351743573): `Ran 406 tests ... OK` (5 pruebas nuevas). La corrección de sintaxis de un test intermedio está incluida.

Repetir **solo el preflight**, descargando la versión nueva:

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/17963e287152afe1cb845f73d460cdfd53b81091/service.cloud.masqelec/tools/rclone_two_mount_fuse_bind_local_lab.py' -O /tmp/rclone_two_mount_fuse_bind_local_lab.py
python3 -m py_compile /tmp/rclone_two_mount_fuse_bind_local_lab.py
python3 /tmp/rclone_two_mount_fuse_bind_local_lab.py --preflight
```

**No ejecutar** `--run-local-pilot --confirm-isolated-only` hasta obtener `RCLONE_MOUNT_FLAGS=YES` y `LAB_RESULT=READY_FOR_LOCAL_PILOT` en ese equipo. En ningún caso los 406 tests prueban mounts reales. El siguiente paso tras validar el preflight sería un ensayo temporal autorizado en `/tmp`, nunca un cambio de `system.d` o de las cuatro rutas Kodi.


## KodiELEC: piloto real 2 FUSE + 4 bind SUPERADO (18-11-2026)

**Evidencia textual proporcionada por el operador**, después del preflight con todas las opciones en `YES`:

```text
LAB_MODE=RCLONE_TWO_FUSE_FOUR_BIND_LOCAL
ONEDRIVE_ACCESSED=NO
RCLONE_LIVE_CONFIG_READ=NO
KODI_PATHS_CHANGED=NO
SYSTEMD_WRITE=NO
GITHUB_UPLOAD=NO
LAB_RESULT=PASS_LOCAL_FUSE_BIND_LAB
```

**Resultado: PASS real del laboratorio LOCAL en KodiELEC**. El programa solo devuelve PASS tras constatar dos montajes FUSE, cuatro bind, lecturas correctas y limpieza final. Sin secretos, no OneDrive, no modificaciones a `system.d`, rutas Kodi o catálogo.

**Corrección de compatibilidad**: unidades actuales de `cloud/develop/system.d` son `Type=simple`; el generador candidato `lib/rclone_two_mount_plan.py` creaba `Type=notify` (sin evidencia de `sd_notify` en el rclone disponible). Ahora genera `Type=simple` sin `NotifyAccess`, al igual que las unidades vigentes. **No están instaladas** las unidades candidatas ni se ha realizado cutover. La preparación privada sigue deshabilitada.

**Pendientes estrictos**: confirmar montaje de `crypt→OneDrive` sin sobrescribir refresh tokens, verificar lectura de una ruta exacta conocida (sin listado global remoto), probar reproducción `.strm`, diseñar espera/orden correcto al arrancar servicios bind bajo `Type=simple` y rollback local real. No activar montajes con el generador actual sin comprobar esas condiciones. MASTER genera catálogo y escanea originales; CLIENTES solo importan `.strm` sin barrido OneDrive.

**No cambiar rclone ni introducir FUSE3** para este objetivo: el binario actual ha superado el montaje FUSE local.
