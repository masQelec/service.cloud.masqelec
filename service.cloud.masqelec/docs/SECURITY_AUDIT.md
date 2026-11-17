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
