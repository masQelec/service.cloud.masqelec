# Handoff — transición rclone 4 FUSE → 2 FUSE + 4 bind
**Fecha:** 2026-11-18 · **Repositorio:** masQelec/service.cloud.masqelec · **Única rama editada:** `develop`

## Decisiones operativas invariables

El addon ya identifica MASTER/CLIENTE; no reescribir roles ni el flujo de catálogo. El MASTER explora los remotos, genera rutas `.strm` y publica un ZIP. CLIENTES importan/difieren el ZIP y escanean los `.strm` locales: **no deben realizar listados periódicos de directorios OneDrive**, y solo acceden a los ficheros remotos al reproducir. Las cuatro rutas originales en los `.strm` deben seguir siendo idénticas:

| Cuenta | Antes (cada uno FUSE) | Después |
|---|---|---|
| OneDrive 1 | `/storage/.mnt/videos/1` | bind de `/storage/.mnt/cloud/1/movies` |
| OneDrive 1 | `/storage/.mnt/tvshows/1` | bind de `/storage/.mnt/cloud/1/tvshows` |
| OneDrive 2 | `/storage/.mnt/videos/2` | bind de `/storage/.mnt/cloud/2/movies` |
| OneDrive 2 | `/storage/.mnt/tvshows/2` | bind de `/storage/.mnt/cloud/2/tvshows` |

Las dos raíces nuevas montan `users_library_1:` y `users_library_2:` respectivamente. Es el rclone antiguo del dispositivo con `Type=simple`, no instalar FUSE3 ni exigir `Type=notify`.

## Evidencia real del usuario (KodiELEC MASTER)

1. `LAB_RESULT=PASS_LOCAL_FUSE_BIND_LAB`: se montaron realmente dos FUSE sobre el backend **local con archivos ficticios**, cuatro bind, lecturas y desmontaje limpio. No probó OAuth.
2. `PREFLIGHT_RESULT=PASS_READ_ONLY` con `CONFIG`, `LEGACY_UNITS`, `LEGACY_MOUNTS`, `LEGACY_SERVICES`, `NEW_MOUNTS_ABSENT`, `NEW_UNITS_ABSENT`, `ROLLOUT_STATE_LEGACY` = PASS. Solo lectura. Confirma que el MASTER mantiene los 4 FUSE legacy sanos y no ha iniciado la nueva arquitectura.

**No repetir** estas dos pruebas salvo cambio real del binario/configuración o nueva hipótesis. **NO se ha probado un corte real con crypt/OneDrive ni reproducido un STRM durante la nueva arquitectura.**

## Código hasta este handoff

Rama `develop`, código validado en commit `8854f331609d7f6467dfbf7ea2f65f4636f9c10c` mediante GitHub Actions [44383466775](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44383466775): **588/588 tests PASS**. Las pruebas nuevas son sintéticas en Python 3.11, con sistema de ficheros temporal real, falsos montajes y comandos systemd simulados; no se ejecutó systemd en KodiELEC.

| Componente | Estado concreto |
|---|---|
| `rclone_two_mount_plan.py` | 2 unidades FUSE `Type=simple`, 4 bind `Type=oneshot` y espera acotada de FUSE; rutas STRM inmutables. |
| `rclone_two_mount_health.py` | valida `mountinfo`, superblock, carpeta y **rechaza montajes apilados** (2 FUSE+4 bind). |
| `service.py::_mounts_ready` | comprobación por `/proc/mounts`/`mountinfo`, **sin `os.listdir` de OneDrive**, tanto en modo legacy como v2; el test de salud no prueba disponibilidad de red. |
| `rclone_two_mount_token_rollback.py` | conciliación pura de dos OneDrive renovados, conserva secciones Google Drive y crypt. |
| `rclone_two_mount_recovery_units.py` | cuatro drop-ins de `ExecStart` que apuntan a `canonical-recovery-candidate.conf` **privado**, sin sustituir el `rclone.conf` compartido. |
| `rclone_two_mount_journal.py` | respaldo canónico y unidades anteriores 0600/0700, `flock`, `fsync` y fases durable `prepared → cutover_started → active/rollback_required → legacy_restored`. |
| `rclone_two_mount_live_adapter.py` | adaptador systemd **desactivado por defecto**, con gates de autorización, reproducción Kodi inactiva, doble FUSE/cuatro bind, lectura exacta de un fichero multimedia por cuenta (15 s), operaciones reversibles y `recover_pending_from_disk()` tras proceso nuevo. `recover_with_local_lock` **requiere habilitación explícita y NO está conectado al arranque**. |
| `rclone_two_mount_boot_guard.py` | comprueba journal y marcador antes de que el addon actualice servicios y bibliotecas. Si recuperación legacy usó tokens rotados, exige que existan y coincidan las cuatro overrides y la config privada; si no, bloquea. |
| `rclone_two_mount_end_to_end.py` | prueba el cambio, error de arranque, tokens rotados, proceso nuevo tras crash, ausencia de una cuenta y reinicio justo tras guardar snapshot antes de instalar. |
| `rclone_two_mount_atomic_install.py` | ficheros candidate-only con no-clobber y permisos cerrados; no modifica producción por sí solo. |

En `mark_cutover_started`, el adaptador persiste journal/marcador y **deshabilita los cuatro servicios legacy antes de pararlos**, de modo que un reboot no los vuelve a montar con tokens potencialmente antiguos durante el cutover. En la activación final, se vuelven a confirmar deshabilitados antes de habilitar los 2+4 nuevos.

### Reversión con refresh OneDrive renovado, sin pisar Google Drive

Después de detener los dos escritores v2, el rollback reconcilia los tokens, escribe `canonical-recovery-candidate.conf` 0600 bajo el journal, instala cuatro drop-ins `rclone_*.service.d/90-masqelec-oauth-recovery.conf`, ejecuta `daemon-reload`, reactiva los cuatro legacy con esa copia privada y confirma montajes. `/storage/.config/rclone/rclone.conf` original **permanece intacto** y Google Drive puede seguir administrando sus propios tokens allí. Los drop-ins persistentes **no se deben borrar** sin migrar con seguridad esas credenciales: el siguiente preflight rechaza nueva transición si los detecta.

En caso de apagón, el motor puede reconstruir `self.baseline`, `self.units`, `self.at_stop` y artefactos instalados desde journal al pedir `recover_with_local_lock`. El guard de arranque falla cerrado si detecta fase incompatible. **No hay autorecuperación invocada por `service.py` ni prueba física tras reboot.**

## Candados de seguridad conservados

```text
RCLONE_TWO_MOUNT_STAGING_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TOKEN_SYNC_ENABLED=False
LIVE_CUTOVER_EXECUTED=NO
REAL_ONEDRIVE_TWO_FUSE_PROBED=NO
SYSTEMD_DROPIN_REAL_KODIELEC_VERIFIED=NO
REAL_REBOOT_RECOVERY_VERIFIED=NO
MASTER_CLIENT_LOGIC_CHANGED=NO
CLOUD_REPOSITORY_MODIFIED=NO
```

Solo `addon/develop` puede cambiar. No tocar `addon/main`, `cloud/develop` ni `cloud/master`.

## Qué sigue, sin crear un proyecto paralelo

1. **Pilotar el adaptador con un laboratorio systemd aislado**, con unidades y rutas temporales y credenciales ficticias; comprobar parsing efectivo de `ExecStart=` en drop-ins y orden `disable legacy → stop → 2 FUSE + 4 bind`, recuperación ante fallo.
2. Repetir el gate de inactividad con `xbmc.executeJSONRPC` REAL, sin reescribir el rol MASTER/CLIENTE. Preparar dos rutas multimedia **ya conocidas** (una por cuenta), sin recorrer OneDrive para descubrirlas.
3. Solo con evidencia favorable, ventana controlada en MASTER para un ensayo de crypt→OneDrive real y reproducción `.strm`, con reversión y recuperación verificadas. **Un PASS en CI no equivale a autorización de cutover.** Nunca pedir ni imprimir tokens.

**Advertencia técnica residual:** systemd puede iniciar unidades al comienzo del boot, antes de ejecutar el addon y su guard. La deshabilitación temprana reduce el riesgo de montar los cuatro legacy durante un corte; todavía se debe probar la secuencia con systemd real y caída de alimentación. El respaldo OAuth privado es duradero pero no garantiza que Microsoft acepte posteriormente cada refresh token; no suponerlo sin prueba real.

## Laboratorio systemd aislado preparado (18-11-2026; NO ejecutado en KodiELEC)

Nuevo script **autocontenido** `tools/rclone_two_mount_systemd_local_lab.py`: preflight exclusivamente lectura; tras confirmación explícita, seis unidades con nombres aleatorios solo en `/run/systemd/system` y dos FUSE + cuatro bind usando fixtures locales solo en `/tmp/masqelec-sd-lab-<16hex>`. Verifica Type=simple, BindsTo/After y bind oneshot con montajes reales, lectura, parada inversa y limpieza obligatoria. No enable, no acceso OAuth, no cambio de rutas Kodi ni servicios legacy; sí realiza `systemctl daemon-reload` global, sin reiniciar servicios. Bloquea un nuevo ensayo si quedan residuos del anterior. **617/617 tests CI PASS** [44391899556](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44391899556), pero NO demuestran systemd/FUSE real en KodiELEC. [Runbook y comandos](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md). Esperar resultado `READY_FOR_ISOLATED_SYSTEMD` del preflight antes de ejecutar el piloto. Flags de migración siguen `False`.

### 18-11-2026 — LAB systemd REAL: arranque fallido y limpieza completa

El operador obtuvo preflight `READY_FOR_ISOLATED_SYSTEMD` (todos YES), seguido de `CLEANUP=COMPLETE` y `LAB_RESULT=FAIL_SERVICE_START`. **NO declarar PASS systemd**. No hay evidencia de afectación de rutas Kodi ni de cambios legacy; no se conocen la fase/unidad ni el motivo. Se ha añadido diagnóstico por `systemctl show` de la unidad efímera que falla (`FAILED_STAGE`, `SYSTEMD_RESULT`, códigos de salida). CI **622/622 PASS** [44394459139](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44394459139); **solo prueba la telemetría, no soluciona todavía el fallo físico**. [Instrucciones y comandos](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md). No actualizar rclone/FUSE3 especulativamente, no activar migración ni tocar producción.

### 18/11/2026 — rclone systemd: causa confirmada, fix pendiente de prueba real

KodiELEC: `BIND_VIDEOS_1` falló con `EXECSTARTPRE_FAILURE` y `CLEANUP=COMPLETE`. Journal: **`/bin/test: No such file or directory` repetido 30 veces**. Corregido tanto el laboratorio de systemd como el generador definitivo de 4 binds: usar builtin `[ -d ... ]` de `/bin/sh`, no `/bin/test`. Tests regresivos añadidos. **624/624 PASS** ([Actions 44399373367](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44399373367)). **El reensayo físico de systemd aún no se ha ejecutado**, cutover OneDrive no autorizado. [Comando y protocolo](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md).

### 18/11/2026 — systemd KodiELEC REAL: PASÓ y limpió

El operador confirma `CLEANUP=COMPLETE`, `LAB_RESULT=PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL` tras corregir `/bin/test` por `[ -d ... ]`. Verificados **dos FUSE rclone y cuatro bind bajo systemd real con backend local**, con lecturas, comprobación de estructura de montajes y limpieza. OneDrive/OAuth no accedidos, rutas de Kodi y unidades legacy intactas, sin unidades permanentes ni habilitaciones. Se cambió además el `ExecStop` FUSE candidato a `/bin/umount`, ya usado en el laboratorio; **624/624 pruebas CI PASS** ([run 44406909094](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44406909094)). El `--real-probe` OAuth continúa bloqueado hasta coordinar escritores MASTER/CLIENTES. **NO** declarar cutover real ni reboot real PASS. [Evidencia y gates](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md).

### 18/11/2026 — inventario OAuth local de flota, sin tokens ni tráfico

Nuevo script `tools/rclone_two_mount_fleet_inventory.py` en `addon/develop`, solo `--inventory`, requiere root. Lee `/proc/PID/comm` y **cmdline local sin imprimirla**, cuenta rclone mount/otros y examina `mountinfo` para cuatro rutas legacy y dos raíces v2; no abre configuraciones, no hace llamadas remotas ni cambia systemd. Cualquier lectura incompleta bloquea. **La captura local NO confirma coordinación de otros dispositivos y NUNCA permite sondeo OAuth**, aunque reporte cero procesos. Ejecutar primero en MASTER y después en cada CLIENTE conocido. [Procedimiento](FLEET_OAUTH_INVENTORY_2026-11-18.md). No desactivar el bloqueo de `--real-probe` ni reiniciar servicios por estos números.

### 18/11/2026 — inventario físico MASTER: PASS_READ_ONLY

KodiELEC MASTER reporta `ROOT=YES`, `PROC_INSPECTION=COMPLETE`, `MOUNTINFO_INSPECTION=COMPLETE`; **4 procesos rclone**, los cuatro clasificados como `mount`, otros **0**, montajes FUSE **4**, rutas legacy **4/4**, raíces v2 **0/2**, apilados **0**, FUSE extra **0**, `INVENTORY_RESULT=PASS_READ_ONLY`. No se inspeccionaron otros dispositivos ni estabilidad entre lecturas: `FLEET_OAUTH_COORDINATION=NOT_VERIFIED`, `REAL_OAUTH_PROBE_ALLOWED=NO`, `CUTOVER_AUTHORIZED=NO`. Próximo paso: inventario del conjunto completo de CLIENTES que compartan credenciales, sin ejecutar OAuth adicional. [Registro íntegro](FLEET_OAUTH_INVENTORY_2026-11-18.md).

### 18/11/2026 — CLIENTE 1: inventario local PASS_READ_ONLY

El usuario identifica como **CLIENTE 1** el equipo con `ROOT=YES`, `PROC_INSPECTION=COMPLETE`, `MOUNTINFO_INSPECTION=COMPLETE`, `RCLONE_PROCESSES=4`, `RCLONE_MOUNT_PROCESSES=4`, `RCLONE_OTHER_PROCESSES=0`, `RCLONE_FUSE_MOUNTS=4`, `LEGACY_MOUNT_TARGETS=4/4`, `V2_FUSE_ROOTS=0/2`, `STACKED_KODI_OR_V2_TARGETS=0`, `OTHER_RCLONE_FUSE_MOUNTS=0`. Ya hay **MASTER + CLIENTE 1** inventariados; ocho montajes y ocho rclone mount reportados entre ambos. **TOTAL_CLIENTS=NOT_CONFIRMED**, no se verificó igualdad/validez OAuth ni totalidad de dispositivos. `FLEET_OAUTH_COORDINATION=NOT_VERIFIED`; `REAL_OAUTH_PROBE_ALLOWED=NO`. [Evidencia](FLEET_OAUTH_INVENTORY_2026-11-18.md).
