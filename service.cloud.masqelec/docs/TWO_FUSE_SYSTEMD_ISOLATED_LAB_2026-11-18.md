# KodiELEC — laboratorio systemd REAL y aislado (2 FUSE + 4 bind)
**18-11-2026 · Estado: laboratorio REAL superado tras fix; `CLEANUP=COMPLETE`, `PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL`. OAuth aún no probado.**

## Propósito

Validar el comportamiento de **Type=simple**, `BindsTo/After`, `Type=oneshot`, espera del FUSE y desmontaje de cuatro bind bajo **systemd real en KodiELEC** antes de cualquier cambio de los montajes OneDrive. No repite innecesariamente el piloto anterior: aquí se prueba la gestión systemd, que estaba pendiente. Rclone sigue siendo el binario KodiELEC ya instalado; el backend es estrictamente LOCAL, con muestras ficticias.

Archivo standalone: `tools/rclone_two_mount_systemd_local_lab.py`, código fijado al commit `3b8e3c5531fd4aec2cdf2246466bf90506f3cb11`.

## Alcance y efectos del ensayo

- `--preflight` **solo lee**: versión/opciones del rclone local, systemctl en funcionamiento, /dev/fuse, montaje y /proc/self/mountinfo, /run/systemd/system y que no queden unidades/rutas de ensayos anteriores. No crea nada.
- `--run-isolated-systemd --confirm-isolated-only` crea `/tmp/masqelec-sd-lab-<16hex>/` modo 0700, dos fuentes de muestra ficticias, dos raíces FUSE y cuatro destinos bind **todos bajo ese /tmp**.
- Crea **seis unidades aleatorias** `masqelec-sd-lab-<16hex>-*.service` exclusivamente bajo `/run/systemd/system` (NO bajo `/storage/.config/system.d`), **sin `systemctl enable`**. Llama `systemctl daemon-reload`, que hace que systemd **relea globalmente** los archivos de unidades pero **no reinicia ni detiene las cuatro unidades legacy**. Inicia/para solo los seis servicios del laboratorio.
- Las unidades FUSE tienen `Type=simple` y `Restart=no`; los cuatro bind dependen de su raíz FUSE por `BindsTo=` y `After=`, esperan la disponibilidad real (máximo 30×1 segundo), comprueban que el destino esté libre y mantienen `Type=oneshot` + `RemainAfterExit=yes`.
- Verifica `/proc/self/mountinfo`: exactamente **dos FUSE independientes** (`device` distinto), cada bind vinculado al superblock, origen y fsroot correspondiente (movies/tvshows), sin apilamiento. Lee `sample.bin` por los cuatro bind usando un subproceso con timeout.
- Limpia en orden inverso: **bind antes que FUSE**; verifica que no quede ningún montaje/proceso activo, elimina solo los seis archivos que siguen idénticos a los propios y la raíz temporal, y realiza el `daemon-reload` final. Si no puede demostrar limpieza, **NO devuelve PASS, no borra directorios con montajes y muestra raíz/prefijo para revisión manual**. Nunca ejecutar un segundo ensayo cuando queden residuos detectables.
- **NO** lee ni escribe `rclone.conf`, remotos crypt/OneDrive, tokens OAuth, unidades legacy, rutas `/storage/.mnt`, catálogo, roles MASTER/CLIENTES, ni `.strm`. Usa `rclone mount /tmp/.../fixtures/N /tmp/.../fuse/N --config /dev/null --read-only --vfs-cache-mode off`. No instala FUSE3.

## Paso 1 — preflight de solo lectura en el MASTER

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/3b8e3c5531fd4aec2cdf2246466bf90506f3cb11/service.cloud.masqelec/tools/rclone_two_mount_systemd_local_lab.py' -O /tmp/rclone_two_mount_systemd_local_lab.py
python3 -m py_compile /tmp/rclone_two_mount_systemd_local_lab.py
python3 /tmp/rclone_two_mount_systemd_local_lab.py --preflight
```

Debe incluir `ROOT=YES`, `FUSE=YES`, `RCLONE_FLAGS=YES`, `SYSTEMD_ONLINE=YES`, `RUNTIME_DIR=YES`, `NO_PRIOR_LAB=YES` y terminar:

```text
LAB_RESULT=READY_FOR_ISOLATED_SYSTEMD
```

Si aparece cualquier NO, **no ejecutar el piloto**; investigar la condición exacta. No copiar configuraciones ni credenciales en el chat.

## Paso 2 — solo tras READY, piloto systemd aislado (crea recursos temporales)

```sh
python3 /tmp/rclone_two_mount_systemd_local_lab.py --run-isolated-systemd --confirm-isolated-only
```

Final válido exclusivamente con **ambas** líneas:

```text
CLEANUP=COMPLETE
LAB_RESULT=PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL
```

**No suponer PASS si solo los montajes funcionaron pero falló la limpieza.** En caso de `FAIL_SYSTEMD_CLEANUP`, NO reiniciar el piloto ni desmontar a ciegas. Comprobar solo lectura:

```sh
grep 'masqelec-sd-lab-' /proc/self/mountinfo
systemctl list-units --all --no-pager 'masqelec-sd-lab-*'
ls -ld /run/systemd/system/masqelec-sd-lab-* 2>/dev/null
```

Comunicar esas salidas para una limpieza guiada que afecte únicamente a los recursos del laboratorio. No usar `umount -a`, no reiniciar servicios rclone legacy y no borrar manualmente /tmp mientras haya FUSE/bind montado.

## Evidencia y límites

Suite GitHub Actions [44391899556](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44391899556) **617/617 pruebas PASS** de Python, incluidas 29 pruebas nuevas del script (prerrequisitos, estructura, orden, no-clobber, fallos y limpieza). **No ejecutan systemd ni FUSE verdaderos en CI**. El laboratorio FUSE local anterior pasó físicamente en KodiELEC, y el preflight legacy MASTER también; este **nuevo** laboratorio systemd sigue pendiente de ejecución por el operador.

Tras confirmar PASS real, aún faltarán cutover real crypt→OneDrive, prueba multimedia exacta por cuenta, Kodi STRM y recuperación física tras un reinicio. La ruta de migración/rollback en `lib/rclone_two_mount_live_adapter.py` sigue desactivada; los tres flags permanecen `False`. No incluir las seis unidades efímeras en ningún paquete desplegable.

**Handoff:** registrar la salida exacta del operador y clasificar fallos sin instalar paquetes ni activar cambios de producción.

## Resultado REAL KodiELEC systemd (18-11-2026) — fallo de arranque con limpieza OK

El operador ejecutó **ambos pasos** del nuevo laboratorio. El preflight devolvió `LAB_RESULT=READY_FOR_ISOLATED_SYSTEMD` con todos los requisitos YES. El piloto real devolvió:

```text
LAB_MODE=RCLONE_2FUSE_4BIND_REAL_SYSTEMD_ISOLATED
ONEDRIVE_ACCESSED=NO
LIVE_RCLONE_CONFIG_READ=NO
KODI_MOUNT_PATHS_CHANGED=NO
LEGACY_SERVICE_START_STOP=NO
LEGACY_UNIT_FILES_CHANGED=NO
SYSTEMD_DAEMON_RELOAD=ISOLATED_RUN_ONLY
SYSTEMD_RUNTIME_UNITS_ONLY=YES
PERMANENT_UNITS_ENABLED=NO
GITHUB_UPLOAD=NO
CLEANUP=COMPLETE
LAB_RESULT=FAIL_SERVICE_START
```

**Conclusión**: no hay PASS de systemd REAL, no se conocen todavía ni el servicio fallido ni su causa. La limpieza del piloto indica que los recursos temporales se retiraron correctamente. No modificar rclone, FUSE3 ni las unidades legacy basándose en esta salida.

**Corregido en `develop`**: al fallar `systemctl start`, el script llama `systemctl show` de la única unidad temporal afectada **antes de limpiar**. Solo imprime campos predefinidos: `FAILED_STAGE`, `FAILED_UNIT`, `SYSTEMD_LOAD`, `SYSTEMD_ACTIVE`, `SYSTEMD_SUBSTATE`, `SYSTEMD_RESULT`, `SYSTEMD_MAIN_STATUS`, `SYSTEMD_PRE_STATUS`, `SYSTEMD_DIAG_CLASS`. Nunca imprime `ExecStart`, contenidos de journal, entorno ni secretos. Mantiene los guards y desmontaje del ensayo. Compatibilidad systemd antiguo: un campo desconocido se muestra como `UNKNOWN`, **no se inventa un motivo**.

Revisión validada: `42b47dbace7b59d04b366586893f681951b55ec1`; CI [44394459139](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44394459139) **622/622 OK**. Estas pruebas no reproducen el fallo físico.

### Diagnóstico recomendado, sin otra operación destructiva

Primero intentar recuperar el error original leyendo el journal local (no cambia servicios):

```sh
journalctl -b --no-pager -o short-iso | grep -F 'masqelec-sd-lab-' | tail -n 40
```

Si no muestra el error de la unidad o la salida es insuficiente, descargar la **versión con diagnóstico fijada** y compilarla:

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/42b47dbace7b59d04b366586893f681951b55ec1/service.cloud.masqelec/tools/rclone_two_mount_systemd_local_lab.py' -O /tmp/rclone_two_mount_systemd_local_lab.py
python3 -m py_compile /tmp/rclone_two_mount_systemd_local_lab.py
python3 /tmp/rclone_two_mount_systemd_local_lab.py --preflight
```

**Solo si** el preflight nuevo sigue en `READY_FOR_ISOLATED_SYSTEMD`, la salida anterior mostró `CLEANUP=COMPLETE`, no se observan residuos y el operador acepta un nuevo ensayo temporal con `daemon-reload`, ejecutar:

```sh
python3 /tmp/rclone_two_mount_systemd_local_lab.py --run-isolated-systemd --confirm-isolated-only
```

Copiar el bloque `FAILED_*`/`SYSTEMD_*` y `CLEANUP`/`LAB_RESULT`. Si la clase es `UNCLASSIFIED`, usar `FAILED_UNIT` de la nueva salida para consultar solo el registro de esa unidad temporal:

```sh
journalctl -b -u 'UNIDAD_FALLIDA_DEL_LAB.service' -n 35 --no-pager
```

Sustituir `UNIDAD_FALLIDA_DEL_LAB.service` por la unidad literal indicada por el script; **no** consultar logs de los servicios legacy ni pegar configuraciones/credenciales. Si `FAIL_SYSTEMD_CLEANUP`, no repetir: conservar la raíz temporal y diagnosticar antes de desmontar o borrar nada.

**Pendientes reales**: causa de `FAIL_SERVICE_START`, primer PASS real de 2 FUSE+4 bind gestionados por systemd, reproducción `.strm` y prueba de recuperación ante reinicio real. Tres banderas `False`, ningún cutover de OneDrive autorizado.

## 18-11-2026 — Causa REAL identificada y corregida en develop, pendiente reensayo físico

La nueva ejecución del operador con diagnóstico produjo `FAILED_STAGE=BIND_VIDEOS_1`, `SYSTEMD_RESULT=exit-code`, `SYSTEMD_PRE_STATUS=1`, `SYSTEMD_DIAG_CLASS=EXECSTARTPRE_FAILURE`, `CLEANUP=COMPLETE` y `LAB_RESULT=FAIL_SERVICE_START`. El journal de la primera ejecución muestra unas 30 repeticiones de:

```text
/bin/sh: line 1: /bin/test: No such file or directory
```

**Causa confirmada:** las unidades bind (tanto el laboratorio en `tools/rclone_two_mount_systemd_local_lab.py` como el generador de producción en `lib/rclone_two_mount_plan.py`) llamaban `/bin/test -d <directorio>`. KodiELEC no proporciona ese ejecutable. Esta llamada provocó el error 1 durante la espera de 30 s de `ExecStartPre`. El registro **no prueba** una avería de OAuth, crypt, rclone ni FUSE.

**Solución aplicada:** sustituida la dependencia por el builtin POSIX `[ -d <directorio> ]` dentro de la misma orden `/bin/sh -c`, manteniendo el guard de punto de montaje, el timeout de 30 intentos, el fail-closed y los paths Kodi. Nuevas pruebas regresivas en `tests/test_rclone_two_mount.py` y `tests/test_rclone_two_mount_systemd_local_lab.py` verifican que los seis servicios se generan sin `/bin/test` y que el bind tiene `[ -d ... ]`. CI **624/624 tests PASS**: [GitHub Actions 44399373367](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44399373367). **No se ha ejecutado aún la versión corregida en KodiELEC real.**

Descargar **versión exacta corregida** y comprobar antes de ejecutar:

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/d79a6fd3d4a64b0d0cf93f76d1fd77fa7d09a95c/service.cloud.masqelec/tools/rclone_two_mount_systemd_local_lab.py' -O /tmp/rclone_two_mount_systemd_local_lab.py && python3 -m py_compile /tmp/rclone_two_mount_systemd_local_lab.py && python3 /tmp/rclone_two_mount_systemd_local_lab.py --preflight
```

Solo si el resultado es `LAB_RESULT=READY_FOR_ISOLATED_SYSTEMD`:

```sh
python3 /tmp/rclone_two_mount_systemd_local_lab.py --run-isolated-systemd --confirm-isolated-only
```

Resultado objetivo: `CLEANUP=COMPLETE` y `LAB_RESULT=PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL`. Si vuelve a fallar, conservar `FAILED_STAGE`, `SYSTEMD_DIAG_CLASS`, `SYSTEMD_PRE_STATUS`, `CLEANUP` y `LAB_RESULT`, **sin activar ni modificar servicios legacy**. Si limpieza incompleta, no repetir el piloto. `systemctl daemon-reload` forma parte del ensayo (relee unidades globales, no reinicia legacy). Nada se ha desplegado en los dispositivos; las banderas continúan en `False`.

**Próximo gate:** obtener PASS físico en el MASTER con esta revisión y luego avanzar a ensayo crypt/OneDrive real bajo autorización operativa. No declarar el problema resuelto en dispositivo solo porque CI pasó.

## 18/11/2026 — RESULTADO REAL: systemd local 2 FUSE + 4 bind PASS, limpieza PASS

El operador ejecutó en el MASTER KodiELEC la **versión corregida** del laboratorio aislado (código `d79a6fd3d4a64b0d0cf93f76d1fd77fa7d09a95c`) y confirmó esta salida final exacta:

```text
LAB_MODE=RCLONE_2FUSE_4BIND_REAL_SYSTEMD_ISOLATED
ONEDRIVE_ACCESSED=NO
LIVE_RCLONE_CONFIG_READ=NO
KODI_MOUNT_PATHS_CHANGED=NO
LEGACY_SERVICE_START_STOP=NO
LEGACY_UNIT_FILES_CHANGED=NO
SYSTEMD_DAEMON_RELOAD=ISOLATED_RUN_ONLY
SYSTEMD_RUNTIME_UNITS_ONLY=YES
PERMANENT_UNITS_ENABLED=NO
GITHUB_UPLOAD=NO
CLEANUP=COMPLETE
LAB_RESULT=PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL
```

**Alcance confirmado:** 2 rclone FUSE con backend LOCAL ficticio, 4 bind bajo unidades temporales de systemd, comprobación de `mountinfo` con dos superblocks diferentes y los cuatro bind exactos, lectura de las cuatro muestras, parada y limpieza completa. Únicamente `/tmp/masqelec-sd-lab-*` y `/run/systemd/system/masqelec-sd-lab-*.service`; `daemon-reload` del gestor systemd, sin stop/start de unidades de producción ni habilitaciones permanentes. No se accedió a OneDrive ni a OAuth. **No repetir laboratorio local superado salvo cambio pertinente del runtime.**

**Histórico del fallo resuelto:** la primera ejecución falló `BIND_VIDEOS_1` por `/bin/test: No such file or directory`, repitiendo 30 veces. Se corrigieron tanto `tools/rclone_two_mount_systemd_local_lab.py` como `lib/rclone_two_mount_plan.py` para usar builtin de `/bin/sh`: `[ -d ... ]`. El reensayo REAL prueba la corrección para unidades del laboratorio. El generador definitivo comparte la corrección y tiene test de regresión, pero **no se ha desplegado ni probado con OneDrive**.

**Mejora adicional post-PASS:** `lib/rclone_two_mount_plan.py::_root_unit` ahora utiliza `ExecStop=/bin/umount <fuse_root>` en vez de `/bin/fusermount -uz`. `/bin/umount` fue utilizado por las unidades del piloto real (limpieza PASS). La parada de unidades de producción con estos parámetros todavía no ha sido ensayada. Suite final [Actions 44406909094](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44406909094) **624/624 PASS**.

### Lo pendiente antes de permitir migración REAL

- `rclone_two_mount_real_probe_lab.py --real-probe` está **bloqueado por diseño** si hay montajes rclone activos y además bloquea si no existe coordinación demostrable entre dispositivos con tokens OneDrive compartidos. No quitar barreras ni lanzar `rclone lsf` sobre cuentas reales por el PASS local. Una simple solicitud remota puede renovar un refresh token e invalidar o desincronizar el de otro cliente.
- Definir ventana de mantenimiento y coordinación MASTER/CLIENTES con comprobación de escritores OAuth, copias privadas 0600 de tokens y rollback; verificar criptografía y lectura de **un archivo conocido por cuenta** sin rastreo de bibliotecas.
- Probar la reproducción `.strm` real de Kodi en las cuatro rutas originales, la restauración efectiva de los cuatro servicios y el comportamiento tras reinicio. `boot_guard` es bloqueo conservador, no un mecanismo de recuperación automática ya probado en KodiELEC real.
- `RCLONE_TWO_MOUNT_STAGING_ENABLED=False`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`, `RCLONE_TOKEN_SYNC_ENABLED=False`. No ha habido despliegue de las seis unidades candidatas ni modificación de cuatro montajes legacy. Sin cambios en `addon/main` ni `cloud/develop/master`.

**GATE REAL_SYSTEMD_LOCAL_2FUSE_4BIND=PASS**; **GATE REAL_ONEDRIVE_2FUSE=NOT_RUN**; **CUTOVER_AUTHORIZED=NO**.
