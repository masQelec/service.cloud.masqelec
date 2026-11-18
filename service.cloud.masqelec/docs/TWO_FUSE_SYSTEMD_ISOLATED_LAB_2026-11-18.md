# KodiELEC — laboratorio systemd REAL y aislado (2 FUSE + 4 bind)
**18-11-2026 · Estado: PREPARADO, aún NO ejecutado físicamente.**

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
