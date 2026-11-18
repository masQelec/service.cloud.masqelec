# Seguridad y auditoría técnica — Cloud masQelec

**Corte:** 17-11-2026 · **Scope:** `service.cloud.masqelec/develop` y `cloud.masqelec/develop`. **No es una certificación de producción.** Se distinguen observaciones de código, pruebas sintéticas y resultados reales de laboratorio comunicados por el operador.

## 1. Inventario de activos y fronteras de confianza

| Activo | Ubicación / comportamiento | Riesgo |
| --- | --- | --- |
| OAuth OneDrive (2) y Google Drive (2) | Secciones en `rclone.conf`; refresh tokens renovables | Pérdida, sustitución o invalidez del token por escritor concurrente |
| Dos wrappers `crypt` | `users_library_1`, `users_library_2`; cifran datos, **no nombres** | Contraseña, ruta o backend cambiados => acceso roto o configuración incorrecta |
| Backup MQC2 | `cloud/develop/rclone/rclone.conf.crypt`; autenticado | Desincronización o publicación de credenciales obsoletas |
| Clave local | Derivada de entrada de `authorized_keys` | Rotación o alteración del material de origen afecta al descifrado |
| Cuatro montajes legacy | Comparten fichero `rclone.conf` | Dos procesos pueden escribir renovaciones de una cuenta simultáneamente |
| Nuevo esquema v2 | Dos archivos privados `account*.conf`, 2 FUSE + 4 bind | Coexistencia de versiones, restart, token único por cuenta **por equipo**, no global |
| GitHub API | Operaciones GET / PUT con SHA de archivo | 409/422 y actualizaciones concurrentes; reintentar sin reevaluar base es inseguro |
| `system.d/` | Descargado en arranque por `cloud_storage.py` | Cambios remotos pueden activar `try-restart` |
| Logs/Telegram/PVR | Tienen rutas y metadatos de los dispositivos | Evitar serializar secretos, URLs con credenciales o líneas de configuración |

Los comandos de laboratorio deben ocultar nombres de cuentas, secretos y stderr de rclone. Solo registrar estados, recuentos, hashes **de código** y marcadores de seguridad. **No publicar hashes de credenciales reales**: tampoco son necesarios en la documentación.

## 2. Hallazgos y tratamiento

| ID | Riesgo / hallazgo | Estado | Evidencia / medida |
| --- | --- | --- | --- |
| SEC-01 | Política antigua omitía remotos OneDrive al seleccionar OAuth | **Mitigado en código `develop`** | `rclone_token_policy.py`: drive + onedrive, 4 tokens; pruebas unitarias |
| SEC-02 | Cambiar unidad OneDrive sin cambiar token provocaría mezcla de identidades | **Mitigado en código** | Se comprueba `drive_id`, `drive_type` y campos de identidad; bloqueo automático |
| SEC-03 | `expiry` de access token usado para ordenar versiones de refresh | **Mitigado en política** | Se compara refresh exacto; no se afirma cuál es posterior sin probe/consistencia |
| SEC-04 | Cuatro montajes comparten escritor `rclone.conf` | **Riesgo activo legacy** | `_config_mounts_active`, fences en `/proc`, lectura estable; lab real PASS; recuperación hot bloqueada |
| SEC-05 | `os.replace` + comparación no son CAS frente a rclone mount | **Pendiente operativo** | Bloqueo de reemplazo con mounts activos; ningún locking mutuo con proceso rclone |
| SEC-06 | Copiar tokens en archivo de prueba puede rotarlos en Microsoft | **Riesgo operativo** | `--real-probe` se bloquea tanto con mounts locales como sin ellos hasta disponer de coordinación verificable de los demás equipos (commits `17cb2901`, `41b9f033`) |
| SEC-07 | Dos wrappers `crypt` desconocidos podían eliminarse al aislar | **Mitigado en código** | Resolución de dependencias `crypt→OneDrive` y conservación exacta; laboratorio 4/4 PASS |
| SEC-08 | Publicador `catalog_utils._upload_file` reintenta con SHA nuevo en 409/422 | **No utilizar para OAuth v2** | `rclone_two_mount_publish_guard.strict_put` hace un PUT máximo; no está conectado |
| SEC-09 | Confundir éxito HTTP PUT con backup definitivamente verificado | **Pendiente integración** | `strict_put` devuelve `accepted_requires_remote_confirmation`; falta relectura independiente |
| SEC-10 | Migración puede sobrescribir unidades al arrancar `cloud_storage` | **Mitigación parcial / no desplegar v2** | Actualizador legacy se bloquea en `active/unsafe`; `cloud/system.d` permanece legacy |
| SEC-11 | `service.py` exigía 4 FUSE; 2 FUSE+4 bind parecerían caídos | **Código preparado, no probado real** | `rclone_two_mount_health.py` valida `mountinfo`; flag v2 False |
| SEC-12 | Dos escritores locales por cuenta en cuatro FUSE | **Diseño v2 lo reduce a uno por equipo** | No elimina conflictos entre MASTER y CLIENTES ni acredita compatibilidad proveedor |
| SEC-13 | Rutas de Kodi/cifrado de nombres cambian por error | **Gates de propuesta PASS** | Rutas legacy invariables, `filename_encryption=off`, `crypt` sin mutación |
| SEC-14 | Descifrado MQC2/archivos de configuración impresos en logs | **Control de laboratorio** | Scripts no imprimen contenido ni stdout/stderr, temporales `0600` |
| SEC-15 | Actualizador de **SO** interpretado como distribuidor del addon v2 | **Gap funcional documentado** | `updater.update_system` no hace rollout del nuevo addon; diseñar canal versionado por dispositivo |
| SEC-16 | No se ha probado rollback de FUSE/bind con reproducción | **BLOQUEANTE** | No activar ni cortar servicios sin piloto con rutas alternativas y ventana inactiva |

**Importante:** *mitigado en código* no significa *verificado en producción*. Algunos controles son barreras previas al despliegue y carecen todavía de integración real.

## 3. Evidencia auditada

| Hito | Evidencia recibida del operador | Alcance y límite |
| --- | --- | --- |
| Inventario MASTER | 6 secciones, 4 OAuth: 2 OneDrive, 2 Drive; 2 `crypt` | Dispositivo real; no incluir secretos |
| Recuperación MASTER | Simulación de corrupción y restauración desde MQC2, `LAB_RESULT=PASS` | Fichero de laboratorio, **no** `rclone.conf` activo |
| Concurrencia | `LIVE_CONFIG_MOUNTS_ACTIVE=YES`, `ISOLATED_CONFIG_MOUNTS_ACTIVE=NO` | Detección /proc, no locking distribuido |
| Aislamiento `crypt` | 4 unidades `CRYPT`, 2 secciones/una, OneDrive 1/una; 0 divergencias; PASS | Configs temporales; no unidades instaladas |
| Plan 2 FUSE + 4 bind | 2 configs, 2 unidades FUSE, 4 bind, rutas 4, permiso 0600; PASS | Solo generación de archivos, **no montaje** |
| Política OAuth v2 | `SIMULATED_ROTATION=REQUIRES_REAL_PROBE`, Google/crypt PASS | Mutación sintética, **sin OAuth real** |
| Suite Ubuntu | `Ran 228 tests in 0.280s; OK` | 17-11-2026, comunicado por el operador |
| Preflight GitHub SHA/MQC2 v2 | **PENDIENTE** | No inventar PASS ni asumir coincidencia de refresh tokens |
| Sondaje OAuth v2 real y montaje FUSE/bind | **NO EJECUTADOS** | Riesgo de refresh remoto/impacto Kodi |

La suite llegó a 228 tras arreglar tres errores de mock: el parámetro `stderr` del runner simulado recibía el entero `subprocess.PIPE` en lugar del texto esperado. Commit de corrección: `46e5960d02302ace8c263c0aafce2bcdbef99eb7`. El operador confirmó después `228/228 OK`.

## 4. Reglas invariantes (auditoría obligatoria)

1. Ninguna credencial real, URL de servicio con contraseña, archivo `authorized_keys` ni secreto `crypt` entra en GitHub en claro, logs o chat.
2. No confundir BACKUP MQC2 autenticado con sesión OAuth válida actualmente: la validez requiere verificaciones controladas.
3. No sobrescribir un refresh token solo por fecha/hora, expiry o SHA nuevo. Toda promoción exige identidad, prueba, revalidación de fuentes y del respaldo remoto.
4. No sustituir un archivo de rclone que un `mount` activo pueda escribir. Los locks de Python **no** coordinan al binario rclone.
5. Nunca habilitar `RCLONE_TOKEN_SYNC_ENABLED` ni `RCLONE_TWO_MOUNT_FEATURE_ALLOWED` sin gate explícito.
6. Los laboratorios que prueban OAuth pueden generar una rotación **en el servidor** aunque trabajen sobre archivos temporales: no hacer `--real-probe` mientras haya montajes activos ni sin evaluar otros CLIENTES.
7. La migración debe conservar las cuatro rutas Kodi, el cifrado de datos y los nombres sin cifrar.
8. Un CLIENTE antiguo debe seguir pudiendo usar el formato MQC2 canónico. Las credenciales v2 no se distribuyen copiando `account1.conf` o `account2.conf` en claro por GitHub.
9. No modificar `cloud/develop/system.d/` sin valorar que `start_cloud_storage` descarga y puede reiniciar automáticamente unidades legacy.
10. Antes de release, probar rollback real, reinicios, desconexiones, cuotas, dos equipos concurrentes, reproducción y persistencia de `prepared/active/unsafe`.

## 5. Auditoría de cambios futuros

Al revisar un PR o commit, comprobar: alcance/HEAD, ramas, dependencias del cambio, presencia accidental de claves, test negativo de identidad, test de fallo/timeout, validación de `crypt`, efecto en CLIENTES legacy, `systemd`/reproducción, concurrencia GH 409/422, observabilidad sin secretos, autorización operativa y reversibilidad.

Clasificar:

- **PASS**: evidencia del control exacto, no del sistema completo.
- **BLOCKED**: barrera de seguridad funcionó; no desbloquear sin causa y autorización.
- **FAIL**: test o invariante incumplido.
- **NOT RUN**: no hay prueba, no se puede inferir aprobación.
- **RESIDUAL**: riesgo aceptado solo si se ha documentado y autorizado explícitamente (ninguna autorización de despliegue v2 concedida).

## 6. Próxima revisión de seguridad

**P0:** preflight GitHub SHA/MQC2 y comparación de refresh. **P0:** estrategia que evite carreras entre dos archivos por equipo y muchos equipos. **P0:** probar FUSE/bind real en rutas no utilizadas y revertirlo. **P0:** ruta de actualización del addon CLIENTE con versiones y no aplicación automática. **P1:** métricas reales de memoria/latencia y caída por cuenta. **P1:** rotación/recovery de claves MQC2 sin bloquear clientes antiguos.

Fuentes de implementación: `lib/rclone_token_policy.py`, `lib/rclone_token_sync.py`, `lib/rclone_two_mount_oauth.py`, `lib/rclone_two_mount_verify.py`, `lib/rclone_two_mount_publish_guard.py`, `lib/cloud_storage.py`, `service.py` y `cloud/system.d/`. Informes antiguos en [docs/README.md](README.md).

## 7. Revisión adicional del preflight (17-11-2026, sin ejecución real)

- `17cb2901` / `41b9f033`: defensa conservadora frente a refrescos entre CLIENTES, y escaneo `/proc` que no declara seguro un `cmdline` truncado o un `mount` desplazado por parámetros. **No se ha probado en KodiELEC**.
- `c701e74e` / `75cb8b48`: el preflight consulta el HEAD de `cloud/develop`, recupera el MQC2 por SHA de commit inmutable y vuelve a comprobar el HEAD. `GH_BRANCH_COMMIT_STABLE=NO` => `INCONCLUSIVE_GITHUB_UPDATED`; no restaura, publica ni toca unidades. Sigue existiendo la limitación de cambios forzados de ref o carrera ajena al lector.
- Se añadieron **5 pruebas unitarias** y quedaron **233/233 PASS** en GitHub Actions (commit `70543894`, run `44188131468`, Python 3.11). La suite de 228/228 sigue siendo evidencia histórica independiente del operador.
- Gate L5 (dispositivo real): **NOT RUN**. Coordinación distribuida OAuth, CAS/readback operativo y montajes reales: **NOT RUN**. No hay autorización de release.


**CI registrado (17-11-2026):** workflow `develop unit tests (no deployment)` con `permissions: contents: read`, checkout sin credenciales persistentes y Python 3.11. Run: https://github.com/masQelec/service.cloud.masqelec/actions/runs/44188131468; `Ran 233 tests in 0.359s / OK`. Esto **no** verifica ejecución en KodiELEC, dispositivos remotos, publicación GitHub MQC2 ni migración real. `main`, `cloud/master`, `cloud/develop/system.d` y montajes no se han modificado.

## Preflight real de KodiELEC: discrepancia OAuth (17-11-2026)

Evidencia del operador (sin credenciales): `MASTER_CANONICAL_LAYOUT=PASS`, `GH_BLOB_SHA_VALID=PASS`, `MQC2_AUTHENTICATED=PASS`, `GH_STATIC_IDENTITY=PASS`, `GH_OAUTH_BASELINE=DIFFERENT`, `LAB_RESULT=BLOCKED_BASELINE_DIVERGED`. El comando fue `--preflight` (`OAUTH_PROBE_REQUESTED=NO`). **Ningún refresh_token puede elegirse como válido/nuevo por esta evidencia**. Puede discrepar OneDrive o Google Drive: la comparación cubre cuatro OAuth. La seguridad del bloqueo es correcta; gate de consistencia L5/P0-A **BLOCKED**, no PASS.

En `develop` se añadió diagnóstico anónimo para las cuatro cuentas: `BASELINE_REFRESH_ONEDRIVE_1`, `BASELINE_REFRESH_ONEDRIVE_2`, `BASELINE_REFRESH_DRIVE_1`, `BASELINE_REFRESH_DRIVE_2` (valores exclusivos `SAME`/`DIFFERENT`; DRIVE numerado por orden de sección). No emite nombres, claves, hashes ni contenido de tokens. Ante divergencia vuelve a leer el fichero local y comprobar `GH_BRANCH_COMMIT_STABLE=YES`; si cambia una fuente devuelve INCONCLUSIVE sin informar un snapshot inconsistente. **No publica, restaura ni sondea OAuth.**

Commits: `f1c6ba1`, `20f924c`, `07b008d`. Suite sintética GitHub Actions: **239/239 OK** (run [44191814025](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44191814025)); incluye dos tests end-to-end del preflight con MQC2 ficticio y cambio de HEAD. **La nueva versión del diagnóstico NO se ha ejecutado todavía en el KodiELEC real.**

Siguiente acción permitida: repetir exclusivamente `--preflight` descargando el script desde el **commit inmutable `07b008db93ad524e9cbfec5b5e0e4b63704fe15e`**; la salida debe indicar qué cuenta difiere, no cuál es más nueva. Si aparece `BLOCKED_BASELINE_DIVERGED`, mantener el bloqueo y conservar las dos fuentes intactas. No ejecutar `--real-probe`, ni modificar `rclone.conf`, `cloud/develop/rclone/rclone.conf.crypt`, unidades, montajes o `main`/`master`.

## Actualización 17-11-2026: P0-B (generaciones) y P0-D (readback), laboratorio

Se incorporaron en `develop` los módulos puros `lib/rclone_two_mount_generation.py` (`5730c0e`) y `lib/rclone_two_mount_readback.py` (`d441ea5`), con **32 pruebas nuevas** sobre el baseline 239. GitHub Actions run [44194785936](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44194785936) confirma **271/271 OK**.

- P0-B: **PASS en simulación**, compara canónico, dos cuentas aisladas y MQC2 mediante huellas HMAC efímeras, SHA/HEAD y cuatro epochs. Distingue cambio local, cambio remoto y ABA **si y solo si** todos los escritores incrementan epochs fiables. No existen en el legacy; con escritores no coordinados `blocked_untracked_writers`.
- P0-D: **PASS parcial sintético**, confirma GET MQC2 autenticado y bytes idénticos, blob SHA esperado, commit HEAD leído estable. `verified_lab_only` **no es autorización**.
- P0-C: **NO IMPLEMENTADO**; múltiples CLIENTES/montajes rclone siguen pudiendo renovar refresh OneDrive. El token local renovado después del backup es la **causa confirmada por operador** del bloqueo P0-A.
- Sin red OAuth, sin GitHub PUT de credenciales, sin migración. `main`, `cloud/master`, `cloud/develop/system.d` intactos. Los dos flags siguen False.
- Documentación técnica: [OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md](OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md).


**Hallazgos nuevos:** SEC-17 — sin contador fiable por cada escritor (los HMAC de snapshots detectan cambio neto, no ABA invisible), **BLOCKED operativo**; SEC-18 — la lectura independiente post-PUT y coordinación interdispositivo no están integradas, **BLOCKED operativo**. Los tests sintéticos no validan que se controle un proceso rclone en vivo. Mantener el caso P0-A bloqueado y no publicar tokens.

## Estado P0-C: protocolo de flota (17-11-2026)

**Última suite CI:** **322/322 OK**, GitHub Actions [44196168382](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44196168382) (Python 3.11, sin Kodi, OAuth real, GitHub PUT ni mounts). Se incorporaron `rclone_two_mount_fleet.py` (commit `64ddba43`, **35 tests**) y `rclone_two_mount_fleet_gate.py` (commit `b5bf5a47`, **16 tests**). Total: **51 tests nuevos** respecto de 271. Los resultados `quiescent_lab_only`, `both_accounts_quiescent_lab_only` y `dual_fence_lab_only` **nunca autorizan publicación**.

- Impide aceptar flota declarada incompleta/no verificada, legacy activo, escritores desconocidos, equipo offline, ack ausente, ack obsoleto, epoch cambiado, cambio de membresía/revisión, expiración, reloj inválido o cohorte incoherente.
- La conjunción de ambos OneDrive + fuentes P0-B **bloquea expresamente `baseline_diverged`**, como ocurre ahora en KodiELEC tras renovación OneDrive posterior al MQC2. No se han seleccionado ni copiado tokens.
- **No hay autoridad real de inventario, attestation autenticada, fencing de procesos rclone, contador global verificable, servicio coordinador, persistencia de leases ni protocolo de reanudación tras crash.** Los booleanos y recibos de los tests son afirmaciones sintéticas; ningún usuario puede convertirlos en una garantía de exclusión.
- Microsoft documenta que al renovar un refresh token no invalida automáticamente el anterior: https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens . La divergencia confirma backup desactualizado, no prueba expiración/revocación de los tokens antiguos ni exige desconectar clientes.
- **Sigue bloqueado:** P0-A coherencia MQC2; P0-C operativo; P0-D PUT/readback real; despliegue P0-E/H. Flags `RCLONE_TOKEN_SYNC_ENABLED=False`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; `cloud/develop/system.d`, `addon/main` y `cloud/master` sin cambios.
- Guía completa: [OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md](OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md).


**Hallazgos SEC-19/SEC-20:** (1) un lock externo no gobierna al escritor OAuth dentro de rclone legacy; (2) los recibos declarados True no autentican equipos, y un lease vencido no demuestra parada del proceso. Protocolo de flota **no implantado**; no permitir que `dual_fence_lab_only` se conecte a `strict_put` ni se trate como aprobación. Ver [P0-C](OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md).


## Aclaración de arquitectura y actualización del addon (17-11-2026)

El operador confirma: MASTER publica el catálogo de biblioteca, los CLIENTES ya reciben versiones del addon y el servicio arranca con el código actualizado. Los .strm apuntan a las **cuatro rutas Kodi existentes** y no requieren que el CLIENTE haga barridos de directorios OneDrive para descubrir archivos. La migración se hace **localmente en el arranque de cada versión definitiva**: leer/preservar credenciales locales, preparar los dos snapshots crypt→OneDrive, y sustituir 4 FUSE por 2 FUSE+4 bind únicamente al tener pruebas de idoneidad y rollback. **No hace falta un coordinador central** para esa migración; la sincronización OAuth entre dispositivos es independiente y sigue bloqueada. El addon todavía no ejecuta el cutover. Ver [ADDON_STARTUP_ROLLOUT_2026-11-17.md](ADDON_STARTUP_ROLLOUT_2026-11-17.md). `startup_decision()` es política pura, no ejecución; GitHub Actions **352/352 OK** (run 44197364926).

**Corrección de prioridad de seguridad:** el bloqueo de refrescos entre equipos no impide por sí mismo reducir los procesos de lectura por dispositivo, siempre que se conserve el token local y no exista sincronización/promoción automática del mismo. Sí seguir exigiendo exclusión de montajes locales durante la sustitución de unidades, reserva/rollback y ausencia de reproducción en ese dispositivo.

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


**Riesgo residual:** un snapshot de `rclone.conf` leído con metadatos estables no sustituye un bloqueo con rclone; si el token cambia después de preparar, el futuro activador deberá revalidar contra fuentes vivas. El staging no otorga acceso ni autoridad de publicación MQC2.

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


## Transición reversible: readiness de FUSE y fusión OAuth local (18-11-2026)

Implementado en `develop`: los cuatro servicios bind generados tienen **espera limitada de FUSE (30 × 1 s)** y se niegan a montarse encima de las cuatro rutas Kodi si ya son mountpoints. Compatibilidad `Type=simple` conservada; no se introduce `Type=notify`. Nuevo `lib/rclone_two_mount_token_rollback.py` **puro** para conservar dos tokens OneDrive aislados al volver a cuatro rclone, sin alterar Google Drive/crypt y bloqueando cambios concurrentes o identidad distinta. **424/424 tests OK** — [GitHub Actions 44356523812](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44356523812). No hay ejecutor de cutover, copias instaladas ni ensayo real de OneDrive; el staging sigue en ruta privada distinta de los `ACCOUNT_CONFS` de las unidades. **NO activar banderas**. [Protocolo y pendientes](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

**Amenaza residual:** `reconcile_canonical_for_rollback` no verifica con Microsoft el refresh nuevo. El ejecutor futuro debe detener el escritor aislado antes de leer el snapshot; un token leído durante una escritura activa no constituye un punto de recuperación consistente. No imprimir ni subir la configuración resultante.

### MASTER listo para preparación; ejecutor live aún bloqueado (18-11-2026)

El operador confirmó `PREFLIGHT_RESULT=PASS_READ_ONLY` con `CONFIG`, `LEGACY_UNITS`, `LEGACY_MOUNTS`, `LEGACY_SERVICES`, `NEW_MOUNTS_ABSENT`, `NEW_UNITS_ABSENT`, `ROLLOUT_STATE_LEGACY` = PASS. Sin OAuth, cambios de sistema ni verificación de playback. Implementados motor puro, gate Kodi JSON-RPC, journal persistente y escritura exclusiva de artefactos, **sin adaptador systemd real**. **507/507 tests PASS** (GitHub Actions [44361419430](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44361419430)); no activación ni rollback operativo. Ver [protocolo](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

**Riesgo principal de release:** journal transaccional y rollback están probados de forma aislada, NO orquestados bajo KodiELEC real. Ausencia de estado persistente de fase antes de `systemctl stop`, OAuth concurrente o arranque inesperado puede dejar rutas Kodi sin disponibilidad. Esto obliga a mantener el corte deshabilitado hasta conexión y ensayos reales del adaptador.

### Adapter local v2, 530/530 CI OK (18/11/2026)

Se añadió `lib/rclone_two_mount_live_adapter.py` al código de `develop` con ejecución explícitamente deshabilitada por defecto y sin integración en `service.py`. Revalida montajes legacy sin apilamientos, usa journal y operaciones systemd limitadas, conserva tokens locales, y exige leer un fichero conocido de cada cuenta antes de marcar ACTIVE (límite 15 s por lectura; no explora OneDrive). CI **530/530 PASS**: [run 44364099119](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44364099119). **NO probado con systemd/OneDrive reales; no cutover, no boot recovery.** Riesgo de escritura OAuth concurrente sobre `rclone.conf` aún sin cerrar. [Detalles y próximos gates](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

**Riesgo de carrera residual:** la comprobación de generación del fichero canónico antes de `os.replace` no evita actualizaciones por un escritor externo entre comprobación y reemplazo. Es condición bloqueante para un rollback que necesite persistir nuevos tokens OneDrive junto a remotos Google Drive concurrentes. Debe cerrarse antes de producción.

### 18/11/2026 — boot guard y OAuth fail-closed

Se incorporó `lib/rclone_two_mount_boot_guard.py` al arranque legacy y al gate de biblioteca, de modo que un journal v2 interrumpido **bloquea** actualización/escaneo sin reiniciar a ciegas los cuatro legacy. La reversión OAuth ya no modifica `rclone.conf` compartido con otros escritores: guarda la copia reconciliada 0600 en journal y solicita recuperación manual si hubo rotación. Las unidades legacy se deshabilitan **antes** de habilitar v2; `execute_with_local_lock` requiere la bandera global habilitada. CI **552/552 OK**: [run 44378128654](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44378128654). **No hay recuperación automática completa tras reinicio ni cutover OneDrive real**. [Estado técnico](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

**Auditoría residual:** `boot_guard` no puede impedir que systemd arranque servicios previamente habilitados ANTES de que comience el addon. El orden disable legacy / enable v2 reduce el riesgo de doble habilitación pero no resuelve por sí solo la recuperación de un apagón. El canónico no se sobrescribe; si dos refresh tokens rotan, el rollback requiere acción controlada.

## Actualización 2026-11-18 — recuperación desde journal y rollback OAuth sin clobber

La última implementación de `addon/develop` incluye **reversión de dos a cuatro montajes con tokens OneDrive renovados mediante cuatro drop-ins systemd privados**, sin escribir en `rclone.conf`; recuperación **explícita** desde journal tras perder RAM por reboot; bloqueo al arranque si falta un drop-in/credencial de recuperación; y health kernel-only sin listados periódicos remotos. La arquitectura MASTER/CLIENTE no cambió. CI **588/588 PASS** en [run 44383466775](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44383466775). Los únicos PASS físicos siguen siendo el piloto 2 FUSE+4 bind LOCAL y el preflight legacy de solo lectura. **Sin activación, sin prueba de systemd drop-in real, sin corte OAuth/OneDrive real, sin recuperación automática en boot.** Documento actualizado: [HANDOFF_2026-11-18_CRASH_RECOVERY.md](HANDOFF_2026-11-18_CRASH_RECOVERY.md).

## Laboratorio systemd aislado preparado (18-11-2026; NO ejecutado en KodiELEC)

Nuevo script **autocontenido** `tools/rclone_two_mount_systemd_local_lab.py`: preflight exclusivamente lectura; tras confirmación explícita, seis unidades con nombres aleatorios solo en `/run/systemd/system` y dos FUSE + cuatro bind usando fixtures locales solo en `/tmp/masqelec-sd-lab-<16hex>`. Verifica Type=simple, BindsTo/After y bind oneshot con montajes reales, lectura, parada inversa y limpieza obligatoria. No enable, no acceso OAuth, no cambio de rutas Kodi ni servicios legacy; sí realiza `systemctl daemon-reload` global, sin reiniciar servicios. Bloquea un nuevo ensayo si quedan residuos del anterior. **617/617 tests CI PASS** [44391899556](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44391899556), pero NO demuestran systemd/FUSE real en KodiELEC. [Runbook y comandos](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md). Esperar resultado `READY_FOR_ISOLATED_SYSTEMD` del preflight antes de ejecutar el piloto. Flags de migración siguen `False`.

### 18-11-2026 — LAB systemd REAL: arranque fallido y limpieza completa

El operador obtuvo preflight `READY_FOR_ISOLATED_SYSTEMD` (todos YES), seguido de `CLEANUP=COMPLETE` y `LAB_RESULT=FAIL_SERVICE_START`. **NO declarar PASS systemd**. No hay evidencia de afectación de rutas Kodi ni de cambios legacy; no se conocen la fase/unidad ni el motivo. Se ha añadido diagnóstico por `systemctl show` de la unidad efímera que falla (`FAILED_STAGE`, `SYSTEMD_RESULT`, códigos de salida). CI **622/622 PASS** [44394459139](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44394459139); **solo prueba la telemetría, no soluciona todavía el fallo físico**. [Instrucciones y comandos](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md). No actualizar rclone/FUSE3 especulativamente, no activar migración ni tocar producción.
