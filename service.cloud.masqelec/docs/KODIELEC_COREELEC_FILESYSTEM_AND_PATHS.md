# KodiELEC (fork de CoreELEC) — Sistema de archivos y rutas operativas

**Referencia técnica transversal para nuevos chats y desarrollo del addon `service.cloud.masqelec`.**
Fecha: 2026-11-19. Rama auditada: `develop`. **Separar evidencia local de convenciones del upstream**.
No contiene secretos ni ejemplos de credenciales.

## 1. Fuente y alcance

KodiELEC es un fork de CoreELEC. Flota del operador: equipos **TX3 y X96 X4**, y equipo **MASTER**.
Sin identificación exacta de SoC, DTB, versión y medio de arranque de cada equipo, **no atribuir**
particiones físicas idénticas a toda la flota.

Referencias contrastadas:
- CoreELEC Wiki, instalación: https://wiki.coreelec.org/coreelec:installce
- CoreELEC Wiki, SSH (usuario root): https://wiki.coreelec.org/coreelec:ssh
- CoreELEC foro, diseño /flash y /storage: https://discourse.coreelec.org/t/can-i-store-media-on-the-sd-card-i-boot-from/9757
- CoreELEC foro, imagen SYSTEM raíz squashfs: https://discourse.coreelec.org/t/full-disk-encryption/5524
- CoreELEC foro, servicios persistentes en system.d: https://discourse.coreelec.org/t/howto-install-ubuntu-vdr-and-x11-within-ce-environment/20542
- CoreELEC foro, enable symlinks: https://discourse.coreelec.org/t/coreelec-as-tv-tuner-server/703

**Modelo general CoreELEC**: la partición de arranque se presenta en `/flash` y normalmente
se monta en solo lectura; la imagen `SYSTEM` proporciona raíz `/` generalmente squashfs
de solo lectura (`/etc`, `/usr`, `/bin` no son destinos adecuados para persistencia).
La partición **escribible y persistente** se monta en `/storage`, normalmente ext4.
La instalación/arranque desde SD, USB y eMMC puede alterar el nombre de bloque `/dev/mmcblk*`.
El usuario habitual de SSH es `root`; no asumir sudo, systemd/paquetes de Ubuntu ni escritura
de /etc. `/tmp` es temporal y no sirve como journal recuperable tras reboot.

## 2. Evidencia REAL del operador (MASTER, 19/11/2026)

```text
df -h /storage
/dev/mmcblk1p2  27.4G total  11.1G usados  16.3G disponibles  40% /storage
df -T /storage
/dev/mmcblk1p2  ext4  28709555  11611546  17093913 (bloques 1K)
```

No deducir medio físico exacto desde el nombre del dispositivo. Preflight anterior:
`CONFIG=PASS`, `LEGACY_UNITS=PASS`, `LEGACY_MOUNTS=PASS`,
`LEGACY_SERVICES=PASS`, `NEW_MOUNTS_ABSENT=PASS`, `NEW_UNITS_ABSENT=PASS`,
`ROLLOUT_STATE_LEGACY=PASS`, `PREFLIGHT_RESULT=PASS_READ_ONLY`.

Nuevo readiness reportó `UNIT_DIRECTORY_SAFE=BLOCKED`,
`JOURNAL_PARENT_SAFE=BLOCKED`, `FREE_SPACE=BLOCKED`; aún no hay `stat`
de los directorios para separar **permisos reales** frente a **ausencia del directorio propuesto**.
El espacio en **/storage** está confirmado y no es un problema de capacidad.
No cambiar permisos a ciegas.

## 3. Rutas de CoreELEC/KodiELEC (diferenciar origen)

| Ruta | Uso | Estado / restricción |
|---|---|---|
| `/`, `/usr`, `/etc`, `/bin` | Sistema, normalmente imagen SYSTEM de solo lectura | NO escribir estado de addon |
| `/flash` | Arranque / kernel / SYSTEM, normalmente RO | NO escribir estado de addon |
| `/storage` | Datos persistentes, ext4 en MASTER | CONFIRMADO por df |
| `/storage/.config/system.d` | Unit files y enlaces persistentes de systemd | Estándar CoreELEC y usado por el addon; permisos concretos del MASTER pendientes |
| `/storage/.config/rclone/rclone.conf` | Configuración canónica local rclone/OAuth | PASS de preflight; nunca imprimir |
| `/storage/.config/rclone/rclone` | Candidato de binario rclone | Existe en búsqueda de binarios; ubicación ejecutada en MASTER pendiente |
| `/storage/.opt/bin/rclone` | Binario alternativo | Pendiente comprobar |
| `/storage/.kodi` | Kodi, addons, userdata y logs | Convención CoreELEC |
| `/storage/.kodi/addons/service.cloud.masqelec` | Addon instalado | Ruta convencional; confirmar en MASTER antes de usar |
| `/storage/.kodi/userdata/addon_data/service.cloud.masqelec` | Datos persistentes por addon | Alternativa convencional, NO adoptada actualmente como journal |
| `/storage/.ssh/authorized_keys` | Clave pública para autenticación SSH / derivaciones existentes | Privado: NO mostrar |
| `/tmp` | Archivos temporales / laboratorios | NO persistente; nada crítico tras reboot |
| `/storage/.mnt` | Raíz elegida por masQelec para FUSE/bind | No universal de CoreELEC |
| `/storage/videos`, `/storage/tvshows` | Archivos locales .strm del catálogo | Inmutables durante cutover |

## 4. Contrato exacto de montaje de masQelec

**MANTENER EXACTOS los cuatro destinos vistos por Kodi y los .strm existentes**:

| Cuenta | Ruta Kodi original | Raíz FUSE candidata + subdirectorio |
|---|---|---|
| 1 | `/storage/.mnt/videos/1` | `/storage/.mnt/cloud/1/movies` |
| 2 | `/storage/.mnt/videos/2` | `/storage/.mnt/cloud/2/movies` |
| 1 | `/storage/.mnt/tvshows/1` | `/storage/.mnt/cloud/1/tvshows` |
| 2 | `/storage/.mnt/tvshows/2` | `/storage/.mnt/cloud/2/tvshows` |

El nuevo diseño usa 2 montajes FUSE rclone + 4 bind; se declaran seis unidades:
`rclone_library_{1,2}.service`,
`masqelec_bind_videos_{1,2}.service`,
`masqelec_bind_tvshows_{1,2}.service`.
No regenerar .strm ni biblioteca; Kodi conserva las cuatro rutas antiguas.
Dos remotos crypt `users_library_1:` y `users_library_2:` usan carpetas
`movies` y `tvshows` respectivamente.

## 5. Rutas PROPUESTAS por el código v2 (no confirmar existencia en MASTER)

- `/storage/.mnt/cloud/{1,2}`: dos nuevas raíces FUSE.
- `/storage/.config/rclone/isolated-mounts/account{1,2}.conf`: configs privadas 0600,
  **la subcarpeta se crea solo si es segura**.
- `/storage/.config/masqelec/rclone-v2-transaction`: journal privado de rollback
  `0700` en ext4.
- `/storage/.config/masqelec/rclone-v2-staging`: preparación sin desplegar.
- `/storage/.config/masqelec/rclone-mount-mode.json`: estado persistente de transición.
- `/storage/.kodi/temp/rclone_library_{1,2}.log`: logs del diseño nuevo.
- `rclone/rclone.conf.crypt` (legacy) y `rclone/rclone-v2.conf.crypt` (v2): rutas
  **relativas al repositorio remoto** `masQelec/cloud.masqelec`, **no rutas locales**.

### Discrepancias / gates pendientes

1. `tools/master_cutover_readiness.py` requiere `/storage/.config/masqelec` **ya existente**,
   privado 0700, y consulta allí `statvfs`; si falta, `JOURNAL_PARENT_SAFE` y
   `FREE_SPACE` fallan conjuntamente. Un preflight de solo lectura correcto debe
   distinguir directorio ausente (creable de forma segura) y espacio comprobado sobre
   `/storage` o ancestro existente en el mismo filesystem, sin escribir nada.
2. `/storage/.config/system.d` es **el destino correcto CoreELEC**, pero no está
   confirmado por `stat` si su modo/propietario cumple con
   `rclone_two_mount_atomic_install._trusted_folder` (UID actual y sin g/o writable).
   El actualizador legacy usa `os.makedirs(...,exist_ok=True)` y no fija chmod;
   no inferir que es 0755, 0775 ni corregirlo a ciegas.
3. `journal.locked()` crea `rclone-v2-transaction` privado `0700` pero no garantiza
   la existencia de su padre `/storage/.config/masqelec`; debe haber bootstrap
   explícito y seguro para primera migración. Antes de un cutover real validar
   orden de creación, permisos, fsync y recuperación tras reinicio.
4. `/storage/.config/system.d` contiene enlaces `*.wants` creados por systemctl,
   no confundirlos con los unit files al auditar.
5. La ruta elegida para el journal **es una decisión del proyecto**, no imposición
   del upstream; operador debe confirmar si prefiere
   `/storage/.config/masqelec` o datos de addon Kodi.
6. Las diferencias de modelo TX3 / X96 X4 requieren comprobar SoC/DTB/boot y soporte
   de FUSE en **cada perfil de hardware**; no asumir layout físico idéntico.

## 6. Operaciones seguras para tomar inventario físico (solo lectura)

```sh
id
mount | grep -E ' on (/|/flash|/storage) '
df -T /storage
for p in /storage/.config /storage/.config/system.d /storage/.config/masqelec \
         /storage/.config/rclone /storage/.kodi /storage/.mnt; do
  if [ -e "$p" ]; then stat -c '%n | tipo=%F | modo=%a | uid=%u gid=%g' "$p"
  else echo "$p NO_EXISTE"; fi
done
```

No ejecutar `mount -o remount,rw /flash`, `chmod -R`, `systemctl stop`,
`rclone lsf` real ni instalación del cutover como parte de un inventario.

## 7. Estado de gates (19/11/2026)

```text
UBUNTU_REGRESSION=PASS_787
MASTER_LEGACY_PREFLIGHT=PASS_READ_ONLY
MASTER_READINESS=BLOCKED_LOCAL_PREREQUISITES
CUTOVER_AUTHORIZED=NO
STRM_FILES_CHANGED=NO
REAL_V2_OAUTH_AND_FUSE=NOT_VERIFIED
```

**Uso en próximo chat:** empezar leyendo este documento y
`docs/TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md`, verificar HEAD de
`develop`, consultar el inventario del dispositivo y corregir los gates pendientes
antes de activar el primer cutover. El operador publica por su cuenta las versiones
del addon en el repositorio Kodi.
