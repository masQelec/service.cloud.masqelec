# Registro de progreso, decisiones y próximos gates

**Corte comprobado:** 17-11-2026. Los resultados de KodiELEC y Ubuntu que figuran como PASS proceden de la salida comunicada por el operador. Los commits se han verificado en GitHub; los cambios de documentación posteriores no constituyen nuevas pruebas de código.

## 1. Estado ejecutivo

**Objetivo:** mantener un MASTER masQelec que publique respaldos OAuth MQC2 compatibles con CLIENTES legacy y futuros CLIENTES v2, reduciendo cada dispositivo de 4 a 2 procesos rclone y conservando las cuatro rutas de Kodi.

**Estado actual:** arquitectura 2 FUSE+4 bind **no desplegada**; CI **371/371 PASS**. Preflight real MQC2: OneDrive 1/2 diferentes por renovación posterior confirmada, Drive 1/2 iguales; P0-A **BLOCKED** por divergencia. P0-B/P0-C/P0-D son simulaciones; coordinación distribuida operativa pendiente.

**Últimos HEAD de código antes de este hito documental:**
- Addon `develop`: `46e5960d02302ace8c263c0aafce2bcdbef99eb7` (fix mock de `stderr`).
- Addon `main`: `c446f937c312524f9f0363d1678ef52a22c296b2` (no tocar).
- Cloud `develop`: `ffc5ee83a33fdde81ebde120c1fef633077b41c4` (solo manifiesto v2 `stage_only`).
- Cloud `master`: `da100abdafcdb1659f99ac7a9b25336bf6e86e47` (no tocar).

**En nuevas sesiones**, consultar los HEAD actuales y no suponer que estos hashes siguen siendo los últimos.

## 2. Hitos con evidencia

| ID | Hito | Resultado / evidencia | Alcance |
| --- | --- | --- | --- |
| H0 | Inventario de cuatro remotos OAuth MASTER + 2 extras | **PASS**: 2 OneDrive, 2 Drive, 2 wrappers `crypt` | Forma del config real |
| H1 | Recuperación de corrupción MASTER contra copia MQC2 | **PASS**: `master_corrupt_pending` → `master_recovered_restart_pending` | Restauración a fichero aislado, no live |
| H2 | Fence de concurrencia de cuatro rclone | **PASS**: config real activa YES, config aislada NO | Detección en KodiELEC |
| H3 | Aislamiento por proceso del wrapper `crypt` | **PASS**: cuatro unidades, 2 cuentas, 0 divergencias; contenido cifrado, nombres no | Generación temporal |
| H4 | Propuesta dos FUSE + cuatro bind | **PASS**: dos configs, 2 unidades FUSE, 4 bind, rutas 4, `0600` | Sin instalación de systemd |
| H5 | Reconciliación OAuth v2 | **PASS**: cambio simulado exige probe, Google/crypt preservados | Lógica en memoria |
| H6 | Publicador SHA + sondaje aislado como componentes | **Unit tests OK** (incluidos en 228) | No integrados ni habilitados |
| H7 | Mock `stderr` de sondeo real | **RESUELTO**: antes 3 errores; corregido commit `46e5960`; 228 PASS después | Error en test, no prueba de bug operativo |
| H8 | Preflight GH contents SHA + MQC2 | **PENDIENTE** | Siguiente ejecución segura |
| H9 | Dos montajes FUSE y bind reales en rutas no operativas | **PENDIENTE** | Sin cortes de Kodi |
| H10 | Reconciliación efectiva de refresh tokens en todos los CLIENTES | **PENDIENTE / BLOQUEANTE** | Concurrencia distribuida |
| H11 | Publicador OAuth v2 completo con CAS/confirmación | **PENDIENTE / BLOQUEANTE** | Código actual solo componente desconectado |
| H12 | Distribución actualizable de addon y migración por dispositivo | **PENDIENTE / BLOQUEANTE** | Solo manifiesto no operativo |
| H13 | Piloto CLIENTE, rollback, reproducción, reinicios | **NO EJECUTADO** | Sin autorización |

### Evidencia de suites

Se recibieron secuencialmente **123**, **137**, **152**, **179**, **202** y **228** pruebas `OK`. Algunos totales intermedios fueron **estimados** durante la implementación, no deben registrarse como superados si no existe la salida. Última evidencia:

```text
Ran 228 tests in 0.280s
OK
```

Estas 228 pruebas son **unitarias** en Ubuntu. El último laboratorio en KodiELEC confirmado fue `TWO_MOUNT_OAUTH_RECONCILIATION_READ_ONLY`, PASS; el siguiente `--preflight` de GH aún no ha sido ejecutado según la conversación.

## 3. Cronología de la arquitectura (17-11-2026)

1. Política OAuth para Drive/OneDrive y seis secciones; fences del fichero compartido.
2. `7decbb8`: corrección de mocks de detección de montajes; suite 123.
3. `adbd506` a `593f9ae`: aislamiento por proceso, corrección de wrappers `crypt`; suites hasta 152.
4. `5cf4196` / `090c09f`: generador de dos FUSE + cuatro bind; control de CLIENTES y manifiesto en `cloud/develop`; suite 179.
5. `6692114` / `7b9b3c9`: política de reconciliación y laboratorio con configuración real; suite 202.
6. `6368669` / `271baf0`: sondeo aislado, control GitHub SHA y fence de sondeo con mounts activos.
7. `46e5960`: corrección del test con `stderr` accidentalmente `subprocess.PIPE`; **228 OK**.

Los commits por prefijo sirven para orientarse; verificar SHAs completos antes de reproducir un experimento fijado a una versión.

## 4. Decisiones vigentes (ADR abreviado)

**ADR-001 — No sustituir tokens con montajes activos.** Sin locking compartido con rclone, el `os.replace` es inseguro. Se eligió fallar cerrado y construir un nuevo esquema de aislamiento.

**ADR-002 — Un proceso FUSE por cuenta y cuatro bind.** Evita dos escritores por cuenta **en un mismo equipo** y conserva rutas Kodi. No elimina las renovaciones entre CLIENTES. Requiere probar rendimiento y disponibilidad.

**ADR-003 — Mantener wrappers `crypt` íntegros.** Cifrado de datos, nombres sin cifrar y secretos idénticos. La selección de remotos sigue dependencias `crypt→OneDrive`.

**ADR-004 — Un único backup MQC2 canónico de seis secciones.** Protege compatibilidad con CLIENTES legacy durante transición; no publicar archivos `account*.conf` en claro.

**ADR-005 — No retry de GitHub 409/422 para OAuth.** Bloquear y reconciliar, jamás continuar con SHA recién leído sin reevaluar tokens; incluso 200 requiere confirmar remoto.

**ADR-006 — Actualizaciones por dispositivo y separación entre preparar/activar.** Manifiesto en `rollouts/`, sin tocar `system.d/`, sin activación remota; el `auto_update` existente es de sistema operativo.

**ADR-007 — Sondeos OAuth no son intrínsecamente read-only en el proveedor.** El laboratorio `--real-probe` se bloquea con mounts locales; coordinar escritor(es) de otros equipos antes de realizar uno.

## 5. Backlog priorizado, definición de terminado

| Prioridad | Trabajo | Hecho solo cuando |
| --- | --- | --- |
| **P0-A** | Ejecutar `--preflight` GitHub SHA+MQC2 en KodiELEC | SHA y autenticación PASS, inventario estático y refresh coherentes **o** divergencia catalogada sin escritura |
| **P0-B** | Gate robusto de generaciones para los dos `account*.conf` + canónico | Simulación de reemplazo concurrente/ABA detectada antes y después del candidato |
| **P0-C** | Manejar rotación OAuth causada por probe y varios CLIENTES | No se pierde refresh local ni global; conflictos no generan overwrite |
| **P0-D** | Publicador MQC2 v2 completo, verificación posterior e idempotencia | GET autenticado, PUT único con SHA, 409 sin retry, readback validado, no secrets/logs |
| **P0-E** | Piloto FUSE/bind en rutas **de ensayo** | 2 FUSE, 4 bind, reproducción/prueba de fichero, fallo de red, reinicio y rollback PASS |
| **P0-F** | Compatibilidad del binario rclone `Type=notify` + systemd | Comprobación en versión exacta de KodiELEC |
| **P0-G** | Distribución/versionado del código del addon en CLIENTES | Paquetes auditados, integridad y staging, sin `try-restart` ni migración accidental |
| **P0-H** | Migración/reversión por dispositivo | Script o unidad transaccional probada, operador autoriza, Kodi sin reproducción, cuatro rutas correctas |
| **P1** | Métricas y supervisión flota | Versiones, modos, estado de montajes y fallos sin exposición de claves |
| **P1** | Plan de rotación MQC2 y recuperación de clave | Recuperación probada sin perder acceso de CLIENTES antiguos |

## 6. Prohibiciones y decisión de release

```text
RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
TWO_MOUNT_RELEASE_AUTHORIZED=NO
TWO_MOUNT_DEPLOY_EXECUTED=NO
TWO_MOUNT_CLIENT_AUTO_ACTIVATE=NO
TWO_MOUNT_LIVE_UNITS_CHANGED=NO
TWO_MOUNT_OAUTH_V2_PUBLISH_ENABLED=NO (no existe activación operativa)
```

Los últimos marcadores son **de estado documental**, no variables de entorno que por sí solas hagan cumplir seguridad. Los dos primeros corresponden a banderas reales en `lib/constants.py`.

## 7. Actualización de este registro

Al cerrar cada hito: guardar salida anónima, máquina/rol, commit de fuente del laboratorio, script exacto y si hubo escritura, subida o reinicio; actualizar tabla, auditoría, próximos gates y [HANDOFF_2026-11-17.md](HANDOFF_2026-11-17.md) (o generar handoff nuevo con fecha). Dejar explícito si algo fue **PASS**, **BLOCKED**, **FAIL** o **NOT RUN**.

**Siguiente acción segura:** [OPERATIONS_AND_TESTING.md](OPERATIONS_AND_TESTING.md) — solo `rclone_two_mount_real_probe_lab.py --preflight`.

## 8. Continuación de 17-11-2026 — endurecimiento sin despliegue

En `service.cloud.masqelec/develop` se añadieron commits `17cb2901`, `41b9f033`, `c701e74e`, `75cb8b48`. Dos cambios: (1) sondeo OAuth real bloqueado por falta de prueba de coordinación global incluso con cero montajes locales; (2) preflight MQC2 anclado a SHA de commit de `cloud/develop` con revalidación del HEAD para impedir aceptar cambios concurrentes del repositorio. `cloud/master`, `cloud/develop/system.d` y `addon/main` permanecen fuera del alcance.

**Gates actualizados:** tests adicionales = 5, **PASS en GitHub Actions**; suite ampliada = 233/233 PASS (`70543894`, run `44188131468`); suite histórica = 228/228 PASS; preflight KodiELEC = **NOT RUN**; publicación OAuth v2 = **NO**; montaje FUSE/bind real = **NOT RUN**. El siguiente paso sigue siendo ejecutar la suite ampliada en Ubuntu y el `--preflight` fijado a `c701e74e` en KodiELEC. El retorno `BLOCKED_FLEET_COORDINATION` de `--real-probe` es intencional. Los gates P0-B/P0-C/P0-D y migración aún no están resueltos.


**CI registrado (17-11-2026):** workflow `develop unit tests (no deployment)` con `permissions: contents: read`, checkout sin credenciales persistentes y Python 3.11. Run: https://github.com/masQelec/service.cloud.masqelec/actions/runs/44188131468; `Ran 233 tests in 0.359s / OK`. Esto **no** verifica ejecución en KodiELEC, dispositivos remotos, publicación GitHub MQC2 ni migración real. `main`, `cloud/master`, `cloud/develop/system.d` y montajes no se han modificado.

### Gate P0-A — discrepancia detectada

El preflight real en KodiELEC devolvió `GH_OAUTH_BASELINE=DIFFERENT` y `LAB_RESULT=BLOCKED_BASELINE_DIVERGED`, con SHA/autenticidad MQC2 e identidad estática PASS. No se conoce qué refresh es posterior/usable, ni se efectuaron modificaciones. `P0-A=BLOCKED` hasta diagnóstico de las cuatro cuentas. Implementado desglose anónimo y recheck local + HEAD GitHub (commits `f1c6ba1`, `20f924c`, `07b008d`); GitHub Actions `239/239 OK`, run `44191814025`. Código aún no probado en dispositivo. El siguiente paso es el preflight fijado a `07b008d`, nunca sondeo OAuth real ni restauración automática.

## 9. Segundo preflight real y topología confirmada — 17-11-2026

### Identidad real de las cuentas y arquitectura prevista (aclaración del operador)

La pareja lógica **1** consta del remoto OAuth OneDrive `library_1` y el wrapper `crypt` `users_library_1`; la pareja lógica **2** utiliza el remoto OAuth `library_2` y el wrapper `crypt` `users_library_2`. El nombre `users_library_*` (plural) es el usado por las unidades y constantes actuales del repositorio. No confundir **remoto OAuth** con **wrapper crypt** ni cambiar sus nombres por esta anotación. La dependencia se valida desde `crypt.remote` al leer la configuración; los nombres OAuth aquí son los comunicados por el operador y no deben deducirse de los tests sintéticos `one_a/one_b`.

| Par | OAuth subyacente | Wrapper `crypt` | Proceso FUSE futuro | Bind a Kodi |
| --- | --- | --- | --- | --- |
| 1 | `library_1` | `users_library_1` | `rclone_library_1.service` → `/storage/.mnt/cloud/1` | `movies` → `/storage/.mnt/videos/1`; `tvshows` → `/storage/.mnt/tvshows/1` |
| 2 | `library_2` | `users_library_2` | `rclone_library_2.service` → `/storage/.mnt/cloud/2` | `movies` → `/storage/.mnt/videos/2`; `tvshows` → `/storage/.mnt/tvshows/2` |

**LEGACY:** cuatro procesos `rclone mount` (vídeos y series por cada `crypt`), cuatro puntos FUSE. **Objetivo aún NO desplegado:** dos procesos `rclone mount` (uno por wrapper/OneDrive) más **cuatro bind mounts**, conservando las mismas rutas Kodi; esto no significa seis procesos rclone. El problema OAuth observado es que **ambos tokens OneDrive** difieren del MQC2; ambos Google Drive coinciden. El cambio estructural no garantiza coordinación de refresh entre dispositivos.


**L5/P0-A:** `MASTER_CANONICAL_LAYOUT=PASS`, `GH_BLOB_SHA_VALID=PASS`, `MQC2_AUTHENTICATED=PASS`, `GH_STATIC_IDENTITY=PASS`, `GH_BRANCH_COMMIT_STABLE=YES`, `LIVE_CONFIG_CHANGED=NO`. Cuentas: `BASELINE_REFRESH_ONEDRIVE_1=DIFFERENT`, `BASELINE_REFRESH_ONEDRIVE_2=DIFFERENT`, `BASELINE_REFRESH_DRIVE_1=SAME`, `BASELINE_REFRESH_DRIVE_2=SAME`. Resultado final `BLOCKED_BASELINE_DIVERGED`. **No hay validación de token ni despliegue.** Continuar con análisis de concurrencia/generaciones sin escrituras.

## 10. Causa de la divergencia corroborada por el operador — 17-11-2026

## Confirmación causal del operador — 17-11-2026

**Causa confirmada por el operador:** después de la publicación del último respaldo MQC2, los procesos `rclone mount` activos renovaron los `refresh_token` de las dos cuentas OneDrive (`library_1` y `library_2`) en la configuración local. El MQC2 de `cloud/develop` retuvo los refresh anteriores. Esta información procede de la confirmación expresa del operador; el preflight por sí solo demostró la diferencia, **no** su secuencia temporal.

- OneDrive 1 y 2: `DIFFERENT`; Google Drive 1 y 2: `SAME`.
- Los datos `crypt` y opciones estáticas mantienen compatibilidad.
- **No se ha demostrado vigencia del refresh local ni invalidación del remoto**, ni se ha coordinado el resto de CLIENTES.
- No restaurar tokens antiguos; **tampoco** publicar automáticamente los locales mientras existan escritores concurrentes.
- El riesgo activo es la falta de reconciliación de renovaciones OAuth; dos procesos FUSE por equipo reducirán los escritores locales, **no** los escritores entre equipos.
- `P0-A` queda con **causa de divergencia identificada**, pero el gate de coherencia OAuth permanece **BLOCKED**.
- Próximos gates P0-B/C/D: generaciones por fuente, detección de cambios concurrentes de ambos remotos y del MQC2, coordinación entre MASTER/CLIENTES, publicación CAS con readback y revalidación independiente en laboratorios sintéticos.
- `RCLONE_TOKEN_SYNC_ENABLED=False`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; sin deploy, reinicios, ni escritura de credenciales en GitHub.


## Actualización 17-11-2026: P0-B (generaciones) y P0-D (readback), laboratorio

Se incorporaron en `develop` los módulos puros `lib/rclone_two_mount_generation.py` (`5730c0e`) y `lib/rclone_two_mount_readback.py` (`d441ea5`), con **32 pruebas nuevas** sobre el baseline 239. GitHub Actions run [44194785936](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44194785936) confirma **271/271 OK**.

- P0-B: **PASS en simulación**, compara canónico, dos cuentas aisladas y MQC2 mediante huellas HMAC efímeras, SHA/HEAD y cuatro epochs. Distingue cambio local, cambio remoto y ABA **si y solo si** todos los escritores incrementan epochs fiables. No existen en el legacy; con escritores no coordinados `blocked_untracked_writers`.
- P0-D: **PASS parcial sintético**, confirma GET MQC2 autenticado y bytes idénticos, blob SHA esperado, commit HEAD leído estable. `verified_lab_only` **no es autorización**.
- P0-C: **NO IMPLEMENTADO**; múltiples CLIENTES/montajes rclone siguen pudiendo renovar refresh OneDrive. El token local renovado después del backup es la **causa confirmada por operador** del bloqueo P0-A.
- Sin red OAuth, sin GitHub PUT de credenciales, sin migración. `main`, `cloud/master`, `cloud/develop/system.d` intactos. Los dos flags siguen False.
- Documentación técnica: [OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md](OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md).


## Estado P0-C: protocolo de flota (17-11-2026)

**Última suite CI:** **322/322 OK**, GitHub Actions [44196168382](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44196168382) (Python 3.11, sin Kodi, OAuth real, GitHub PUT ni mounts). Se incorporaron `rclone_two_mount_fleet.py` (commit `64ddba43`, **35 tests**) y `rclone_two_mount_fleet_gate.py` (commit `b5bf5a47`, **16 tests**). Total: **51 tests nuevos** respecto de 271. Los resultados `quiescent_lab_only`, `both_accounts_quiescent_lab_only` y `dual_fence_lab_only` **nunca autorizan publicación**.

- Impide aceptar flota declarada incompleta/no verificada, legacy activo, escritores desconocidos, equipo offline, ack ausente, ack obsoleto, epoch cambiado, cambio de membresía/revisión, expiración, reloj inválido o cohorte incoherente.
- La conjunción de ambos OneDrive + fuentes P0-B **bloquea expresamente `baseline_diverged`**, como ocurre ahora en KodiELEC tras renovación OneDrive posterior al MQC2. No se han seleccionado ni copiado tokens.
- **No hay autoridad real de inventario, attestation autenticada, fencing de procesos rclone, contador global verificable, servicio coordinador, persistencia de leases ni protocolo de reanudación tras crash.** Los booleanos y recibos de los tests son afirmaciones sintéticas; ningún usuario puede convertirlos en una garantía de exclusión.
- Microsoft documenta que al renovar un refresh token no invalida automáticamente el anterior: https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens . La divergencia confirma backup desactualizado, no prueba expiración/revocación de los tokens antiguos ni exige desconectar clientes.
- **Sigue bloqueado:** P0-A coherencia MQC2; P0-C operativo; P0-D PUT/readback real; despliegue P0-E/H. Flags `RCLONE_TOKEN_SYNC_ENABLED=False`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; `cloud/develop/system.d`, `addon/main` y `cloud/master` sin cambios.
- Guía completa: [OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md](OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md).


**Prioridad siguiente:** inventario no invasivo de procesos y dispositivos, elección entre propiedad central/grants independientes y diseño de un escritor que realmente respete el fencing. No ejecutar `rclone lsf`, `config reconnect`, desinstalación ni paradas para obtener PASS.


## Aclaración de arquitectura y actualización del addon (17-11-2026)

El operador confirma: MASTER publica el catálogo de biblioteca, los CLIENTES ya reciben versiones del addon y el servicio arranca con el código actualizado. Los .strm apuntan a las **cuatro rutas Kodi existentes** y no requieren que el CLIENTE haga barridos de directorios OneDrive para descubrir archivos. La migración se hace **localmente en el arranque de cada versión definitiva**: leer/preservar credenciales locales, preparar los dos snapshots crypt→OneDrive, y sustituir 4 FUSE por 2 FUSE+4 bind únicamente al tener pruebas de idoneidad y rollback. **No hace falta un coordinador central** para esa migración; la sincronización OAuth entre dispositivos es independiente y sigue bloqueada. El addon todavía no ejecuta el cutover. Ver [ADDON_STARTUP_ROLLOUT_2026-11-17.md](ADDON_STARTUP_ROLLOUT_2026-11-17.md). `startup_decision()` es política pura, no ejecución; GitHub Actions **352/352 OK** (run 44197364926).

## Fase siguiente: staging privado en el arranque (18-11-2026)

Código en `develop` (commit `3553df3b`, corrección de fixture de test `c782b1c2`): se ha integrado en la fase 1 de `service.py`, **después** de `start_cloud_storage()`, la llamada a `lib/rclone_two_mount_startup_stage.py`. Está protegida por un nuevo flag real:

```python
RCLONE_TWO_MOUNT_STAGING_ENABLED = False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED = False
RCLONE_TOKEN_SYNC_ENABLED = False
```

Con el flag de staging `False`, no se invocan las lecturas ni el generador y no se escribe ningún fichero; el código legacy sigue igual. En una versión futura **expresamente habilitada**, con credenciales locales válidas, generará un staging privado de **dos configs OneDrive+crypt, seis propuestas de unidades y un manifiesto sin secretos**, partiendo del `rclone.conf` local ya renovado por el propio rclone. No consulta OAuth, no usa tokens del MQC2 para sustituir los locales, no recorre directorios OneDrive, no instala unidades ni toca los cuatro montajes Kodi.

Ubicación RESERVADA para esa versión futura (no creada en ningún equipo por estos commits): `/storage/.config/masqelec/rclone-v2-staging/2026-11-17-two-fuse-v1/`. Permisos: directorio raíz y candidato `0700`; `account1.conf`, `account2.conf` y manifiesto `0600`; propuestas de unidades `0644` dentro del directorio privado. El manifiesto distingue `credential_source=existing_local_config_unverified`, `activation=stage_only` y `live_install_allowed=false`. **No afirmar que MQC2 haya sido autenticado por el staging**: no lo descarga.

Controles: valida inventario `crypt→OneDrive`, las cuatro unidades legacy compatibles, fuentes locales regulares (no enlaces simbólicos) y configuración `0600`; comprueba datos y metadatos de origen antes/después de generar; prepara un directorio temporal privado y lo mueve a su destino final sin tocar `system.d`. Reintento con la misma fuente = `already_staged` sin reescribir. Si rclone renovó después el refresh local y el contenido staged difiere, = `blocked_stale_or_unsafe_stage`: **el borrador antiguo no se instala ni se reescribe automáticamente**. La recuperación/reemplazo versionado del staging obsoleto y el cutover reversible se implementarán más adelante; no forzar etapas.

**Evidencia:** fallo inicial del test por no modificar el token ficticio correcto, corregido sin cambiar código de producción; CI final en [GitHub Actions run 44201463687](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44201463687) = **371/371 OK**, 19 pruebas nuevas. Es prueba sintética de filesystem aislado, **no** ejecución en KodiELEC ni autorización de migración.

Próximo paso: piloto de verificación read-only de prerrequisitos KodiELEC y, posteriormente, **dos FUSE + cuatro bind exclusivamente en rutas alternativas**, prueba de reproducción y rollback. El modo operativo legacy seguirá intacto hasta autorización explícita.


## Piloto 2 FUSE + 4 bind en rutas aisladas (18-11-2026)

Nuevo script standalone `tools/rclone_two_mount_fuse_bind_local_lab.py` para KodiELEC: `--preflight` **solo lectura**, y `--run-local-pilot --confirm-isolated-only` (monta dos fuentes **locales ficticias** y cuatro bind en una ruta aleatoria de `/tmp`, valida lecturas y desmonta). No usa `rclone.conf`, tokens OneDrive, `crypt`, rutas `.strm`, `systemd` ni cambios en catálogo. `rclone_two_mount_health.check_layout_at` permite validar rutas temporales sin modificar la comprobación original de Kodi; se preservó el error `ValueError` en `mountinfo` truncado. **401/401 tests CI PASS**, [run 44339477354](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44339477354). **Ningún piloto FUSE/bind real se ha ejecutado todavía en KodiELEC**. El paso siguiente es obtener salida del preflight y, si procede, ejecutar el piloto local controlado antes de probar OneDrive real y `Type=notify`. Ver [procedimiento](TWO_FUSE_FOUR_BIND_LOCAL_LAB_2026-11-18.md).


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


## Transición reversible: readiness de FUSE y fusión OAuth local (18-11-2026)

Implementado en `develop`: los cuatro servicios bind generados tienen **espera limitada de FUSE (30 × 1 s)** y se niegan a montarse encima de las cuatro rutas Kodi si ya son mountpoints. Compatibilidad `Type=simple` conservada; no se introduce `Type=notify`. Nuevo `lib/rclone_two_mount_token_rollback.py` **puro** para conservar dos tokens OneDrive aislados al volver a cuatro rclone, sin alterar Google Drive/crypt y bloqueando cambios concurrentes o identidad distinta. **424/424 tests OK** — [GitHub Actions 44356523812](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44356523812). No hay ejecutor de cutover, copias instaladas ni ensayo real de OneDrive; el staging sigue en ruta privada distinta de los `ACCOUNT_CONFS` de las unidades. **NO activar banderas**. [Protocolo y pendientes](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

## Diagnóstico REAL y seguro antes del corte (18-11-2026)

El operador pidió avanzar rápido hacia la transición, conservando la distinción funcional existente MASTER/CLIENTES y sin cortar reproducción a ciegas.

**Implementado:** `tools/rclone_two_mount_transition_preflight.py` es un solo archivo descargable por SSH y **exclusivamente lectura**. Su `--preflight` verifica la configuración canónica `rclone.conf` (dos cadenas crypt→OneDrive con refresh, dos Drive), que las cuatro unidades legacy siguen apuntando al canónico y usan `--read-only`, cuatro FUSE reales activos y sin apilamientos, cuatro servicios `systemctl is-active`, ausencia de nuevas raíces y unidades v2 instaladas y ausencia de marcador de transición. No escribe a `/storage`, no envía credenciales, no realiza OAuth y no modifica montajes/systemd. Nunca revela contenido del config. La salida sólo indica PASS/BLOCKED. Un resultado `PASS_READ_ONLY` **NO autoriza** el cutover ni comprueba reproducción inactiva.

**Descarga fijada a la revisión de código validada**:

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/a6d4d70f8a9a361a1b148654d7a52a07c18d38e3/service.cloud.masqelec/tools/rclone_two_mount_transition_preflight.py' -O /tmp/rclone_two_mount_transition_preflight.py && python3 -m py_compile /tmp/rclone_two_mount_transition_preflight.py && python3 /tmp/rclone_two_mount_transition_preflight.py --preflight
```

**Evidencia:** [GitHub Actions 44358176820](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44358176820) con `Ran 440 tests ... OK` (16 nuevas pruebas del preflight). La primera ejecución no pasó por un fixture sintético que no modificaba el refresh correcto; corregido y CI final PASS. No confundir con fallo del dispositivo.

Salida deseada:

```text
CONFIG=PASS
LEGACY_UNITS=PASS
LEGACY_MOUNTS=PASS
LEGACY_SERVICES=PASS
NEW_MOUNTS_ABSENT=PASS
NEW_UNITS_ABSENT=PASS
ROLLOUT_STATE_LEGACY=PASS
PREFLIGHT_RESULT=PASS_READ_ONLY
```

**PENDIENTES:** prueba real de inactividad Kodi, ubicación segura y durable de los dos snapshots 0600 y su instalación transaccional, secuencia ejecutora con rollback comprobado tras caídas, ensayo de credenciales/crypt/OneDrive real y reproducción. `CUTOVER_EXECUTOR=NOT_IMPLEMENTED`, `CUTOVER_AUTHORIZED=NO`, los tres flags quedan `False`. Mientras esto no exista, no ejecutar `systemctl stop` ni tocar `/storage/.mnt/`. Los montajes de producción siguen intactos.


### MASTER listo para preparación; ejecutor live aún bloqueado (18-11-2026)

El operador confirmó `PREFLIGHT_RESULT=PASS_READ_ONLY` con `CONFIG`, `LEGACY_UNITS`, `LEGACY_MOUNTS`, `LEGACY_SERVICES`, `NEW_MOUNTS_ABSENT`, `NEW_UNITS_ABSENT`, `ROLLOUT_STATE_LEGACY` = PASS. Sin OAuth, cambios de sistema ni verificación de playback. Implementados motor puro, gate Kodi JSON-RPC, journal persistente y escritura exclusiva de artefactos, **sin adaptador systemd real**. **507/507 tests PASS** (GitHub Actions [44361419430](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44361419430)); no activación ni rollback operativo. Ver [protocolo](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### Adapter local v2, 530/530 CI OK (18/11/2026)

Se añadió `lib/rclone_two_mount_live_adapter.py` al código de `develop` con ejecución explícitamente deshabilitada por defecto y sin integración en `service.py`. Revalida montajes legacy sin apilamientos, usa journal y operaciones systemd limitadas, conserva tokens locales, y exige leer un fichero conocido de cada cuenta antes de marcar ACTIVE (límite 15 s por lectura; no explora OneDrive). CI **530/530 PASS**: [run 44364099119](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44364099119). **NO probado con systemd/OneDrive reales; no cutover, no boot recovery.** Riesgo de escritura OAuth concurrente sobre `rclone.conf` aún sin cerrar. [Detalles y próximos gates](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### 18/11/2026 — boot guard y OAuth fail-closed

Se incorporó `lib/rclone_two_mount_boot_guard.py` al arranque legacy y al gate de biblioteca, de modo que un journal v2 interrumpido **bloquea** actualización/escaneo sin reiniciar a ciegas los cuatro legacy. La reversión OAuth ya no modifica `rclone.conf` compartido con otros escritores: guarda la copia reconciliada 0600 en journal y solicita recuperación manual si hubo rotación. Las unidades legacy se deshabilitan **antes** de habilitar v2; `execute_with_local_lock` requiere la bandera global habilitada. CI **552/552 OK**: [run 44378128654](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44378128654). **No hay recuperación automática completa tras reinicio ni cutover OneDrive real**. [Estado técnico](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

## Actualización 2026-11-18 — recuperación desde journal y rollback OAuth sin clobber

La última implementación de `addon/develop` incluye **reversión de dos a cuatro montajes con tokens OneDrive renovados mediante cuatro drop-ins systemd privados**, sin escribir en `rclone.conf`; recuperación **explícita** desde journal tras perder RAM por reboot; bloqueo al arranque si falta un drop-in/credencial de recuperación; y health kernel-only sin listados periódicos remotos. La arquitectura MASTER/CLIENTE no cambió. CI **588/588 PASS** en [run 44383466775](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44383466775). Los únicos PASS físicos siguen siendo el piloto 2 FUSE+4 bind LOCAL y el preflight legacy de solo lectura. **Sin activación, sin prueba de systemd drop-in real, sin corte OAuth/OneDrive real, sin recuperación automática en boot.** Documento actualizado: [HANDOFF_2026-11-18_CRASH_RECOVERY.md](HANDOFF_2026-11-18_CRASH_RECOVERY.md).

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
