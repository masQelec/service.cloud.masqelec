# Operaciones, pruebas y diagnóstico — masQelec

**Ámbito:** pruebas sin corte de reproducción. Suite CI actual de `develop`: **440/440 OK** (GitHub Actions run 44358176820). Preflight real BLOCKED por refresh OneDrive divergentes tras renovación rclone confirmada. P0-B/P0-C/P0-D: laboratorios, **no** despliegue ni sincronización.

## 1. Protocolo de cambios

1. Leer [HANDOFF_2026-11-17.md](HANDOFF_2026-11-17.md), revisar HEAD de ambos `develop` y ejecutar `git status --short`. No asumir árbol local limpio.
2. Identificar si el cambio afecta a **addon**, **cloud**, **system.d**, **OAuth**, **Kodi** o a un **CLIENTE real**; clasificar riesgo.
3. Trabajar en `service.cloud.masqelec/develop`, sin nuevas ramas salvo necesidad justificada; conservar `main`.
4. Añadir prueba con entorno sintético sin Kodi ni red, ejecutarla y registrar resultado.
5. Para integración KodiELEC: usar laboratorio de `tools/` **solo lectura**, código fijado a commit y salidas que no incluyan secretos.
6. Si hay cambio a `cloud/develop/system.d/`, **detener el cambio** hasta revisión: el arranque actual puede descargar unidades y ejecutar `try-restart`.
7. Registrar evidencia, límites, riesgo residual, rollback y siguiente decisión en [ROADMAP_AND_PROGRESS.md](ROADMAP_AND_PROGRESS.md). No subir ni copiar tokens.

### Comprobación en Ubuntu

```bash
cd ~/GitHub/service.cloud.masqelec
git switch develop
git fetch origin
git status --short
git log -1 --oneline
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

La suite se diseñó sin dependencias de Kodi y con mocks. **Última evidencia externa:** `Ran 228 tests in 0.280s / OK`. No atribuir este resultado a un commit posterior sin repetirla.

### Comprobaciones no invasivas en KodiELEC

```bash
# Estado de procesos/montajes (lectura)
systemctl is-active rclone_tvshows_1.service rclone_tvshows_2.service \
  rclone_videos_1.service rclone_videos_2.service
cat /proc/self/mountinfo | grep -E '(/storage/\.mnt/(videos|tvshows)/[12]|/storage/\.mnt/cloud/[12])'

# Preflight MQC2 remoto y SHA; NO realiza consultas OAuth a Microsoft
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/c701e74e5a677e3d300094f9ea112eb830749c3f/service.cloud.masqelec/tools/rclone_two_mount_real_probe_lab.py' \
  -O /tmp/rclone_two_mount_real_probe_lab.py
python3 -m py_compile /tmp/rclone_two_mount_real_probe_lab.py
python3 /tmp/rclone_two_mount_real_probe_lab.py --preflight
```

El preflight necesita HTTPS a GitHub y acceso local a la clave de dispositivo, pero **no sube** credenciales. Si `GH_OAUTH_BASELINE=DIFFERENT` o `LAB_RESULT=BLOCKED_BASELINE_DIVERGED`, **no publicar ni restaurar**: investigar las dos copias sin sustituir ninguna.

### Laboratorios de referencia

| Script bajo `service.cloud.masqelec/tools/` | Alcance | Evidencia a 17-11-2026 |
| --- | --- | --- |
| `master_oauth_recovery_lab.py --mount-check-only` | Detecta escritores rclone por `/proc` | `LIVE_CONFIG_MOUNTS_ACTIVE=YES`, `ISOLATED_CONFIG_MOUNTS_ACTIVE=NO`, PASS |
| `master_oauth_recovery_lab.py` | Simula corrupción/recuperación MASTER en `/tmp` | PASS (reserva real, 6 secciones) |
| `rclone_mount_isolation_lab.py` | Genera cuatro configuraciones aisladas y wrappers `crypt` | PASS; 4/4, 2 cuentas, 0 divergencias |
| `rclone_two_mount_plan_lab.py` | Genera 2 configuraciones, 2 FUSE y 4 bind; **no instala** | PASS |
| `rclone_two_mount_oauth_lab.py` | Rotación ficticia y reconciliación OAuth en memoria | PASS |
| `rclone_two_mount_real_probe_lab.py --preflight` | Lee MQC2 GitHub, SHA Git y compara estructura/tokens | **PENDIENTE** |
| `rclone_two_mount_real_probe_lab.py --real-probe` | Potencial renovación OAuth remota | **BLOQUEADO aun sin mounts locales**; falta coordinación entre CLIENTES |

**No reutilizar laboratorios antiguos sin leer sus parámetros**: algunos validan credenciales reales con `lsf`, cuya renovación puede afectar a otros escritores. Los resultados históricos deben interpretarse según las versiones fijadas de los scripts.

## 2. Interpretación de estados y errores

| Resultado | Acción |
| --- | --- |
| `LAB_RESULT=PASS` | Registrar alcance, commit y restricciones. **No** activar releases automáticamente. |
| `LAB_RESULT=ERROR_*` / `LAB_FAILED_AT=...` | Investigar módulo y fase exacta; no imprimir tokens ni el fichero real. |
| `BLOCKED_ACTIVE_MOUNTS` | Bloqueo local esperado; no desmontar solo para obtener PASS. |
| `BLOCKED_FLEET_COORDINATION` | Aunque no haya mounts locales, no existe coordinación entre CLIENTES; no habilitar probe. |
| `GH_BRANCH_COMMIT_STABLE=NO` | GitHub `cloud/develop` cambió durante preflight; resultado inconcluso y ninguna escritura. |
| `BLOCKED_BASELINE_DIVERGED` | El backup MQC2 y el canónico contienen distintos refresh tokens; no ordenar por `expiry` ni por mtime. |
| `BLOCKED_STATIC_IDENTITY` / `GH_STATIC_IDENTITY=MISMATCH` | Cambiaron secciones/identidad; no fusionar automáticamente. |
| `429`, `RATE_LIMITED`, `UNAVAILABLE` | No implica OAuth inválido; evitar reintentos repetitivos. |
| `401`, `invalid_grant` | Señal de AUTH potencial; validar contexto y recuperación sin escribir con mount activo. |
| `409/422` en PUT GitHub OAuth | **Conflicto bloqueante**. No refrescar SHA para insistir con el mismo token. |
| Unidad marcada `unsafe` | Bloquear actualizador de montajes legacy, revisar marcador y versión. |

**No ejecutar por probar:** `systemctl try-restart`, `restart`, `stop`, `mount --bind`, `umount`, cambios de `rclone.conf` activo, subida MQC2, modificaciones de `system.d/` y ninguna activación del marcador `active`.

## 3. Matriz de gates

| Gate | Criterio | Estado |
| --- | --- | --- |
| U1 — unitario | Todo `unittest discover` sin errores | **PASS 228/228** (confirmado por operador) |
| L1 — concurrencia legacy | Detectar montajes activos y config aislada | **PASS**, KodiELEC |
| L2 — credenciales `crypt` | 4 unidades, 2 cuentas, opciones sin alterar | **PASS**, KodiELEC |
| L3 — plan FUSE/bind | 2 conf + 2 servicios FUSE + 4 bind; sin instalación | **PASS**, KodiELEC |
| L4 — política OAuth v2 | Rotación ficticia exige probe, Google/crypt intactos | **PASS**, KodiELEC |
| L5 — GitHub MQC2 preflight | SHA del blob, autenticidad MQC2 e inventario coherente | **PENDIENTE** |
| L6 — procesos FUSE/bind reales en rutas alternativas | Montaje, lectura, rendimiento, error/reinicio y rollback | **PENDIENTE** |
| L7 — OAuth v2 operativo | CAS + revalidación concurrente + coexistencia de CLIENTES | **PENDIENTE** |
| R1 — release per-device | Autorización expresa, ventana sin reproducción, rollback probado | **NO AUTORIZADO** |

## 4. Lista de comprobación de una sesión

Antes: guardar hash HEAD + entorno + inventario de pruebas + `RCLONE_TOKEN_SYNC_ENABLED=False` y `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`. Comprobar que el script descargado apunta a su referencia inmutable y no mezcla código de otro addon instalado.

Durante: analizar cada error sin sobrescribir una configuración potencialmente válida. En operaciones de red, controlar timeouts y límites de tasa. No lanzar múltiples procesos de sondeo OAuth en paralelo por la misma cuenta.

Después: dejar la rama `develop` documentada; actualizar [auditoría](SECURITY_AUDIT.md) y [handoff](HANDOFF_2026-11-17.md). Registrar resultados de Ubuntu y KodiELEC **por separado**. La ausencia de fallos unitarios no implica prueba en el dispositivo.

## 5. Plantilla de evidencia

```text
Fecha/hora local:
Repositorio / rama / HEAD:
Máquina: Ubuntu de desarrollo | KodiELEC MASTER | KodiELEC CLIENTE
Acción: prueba unit | preflight | laboratorio sin montaje | otro
Comando:
Resultado: PASS | FAIL | BLOCKED | INCONCLUSIVE
Marcadores relevantes (sin nombres de cuentas ni tokens):
¿Escritura live? NO / ¿Reinicio? NO / ¿Upload? NO
Riesgo residual:
Siguiente gate y responsable:
```

## 6. Reversión — criterio, no comando automático

El rollback v2 exige detener nuevos bind sin producción activa, parar procesos FUSE nuevos, restaurar unidades y configs legacy guardadas, iniciar y verificar las cuatro rutas Kodi. **Este procedimiento aún no ha sido ensayado**; no convertirlo en script operativo sin validación en dispositivo aislado y ventana coordinada. Si falla un ensayo de solo lectura, simplemente conservar los montajes actuales y no iniciar cutover.

Más contexto: [CLIENT_ROLLOUT.md](CLIENT_ROLLOUT.md), [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

## 7. Gate posterior al endurecimiento

Código fijado del script: `c701e74e5a677e3d300094f9ea112eb830749c3f`; el script mantiene sus librerías internas ancladas a su `SOURCE_REF` independiente. El preflight obtiene `cloud/develop` mediante HTTPS, lee el MQC2 en esa **revisión inmutable** y vuelve a comparar la revisión. Resultado adicional exigible: `GH_BRANCH_COMMIT_STABLE=YES`. Si falla, **no** actualizar credenciales ni intentar la publicación. Nuevas pruebas en `test_rclone_two_mount_probe_fence.py` (**5 añadidas; 233/233 PASS en GitHub Actions, run `44188131468`**). Ejecutar primero `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'` en Ubuntu. Ni la prueba de unidad ni esta documentación sustituyen el gate L5 en KodiELEC.


**CI registrado (17-11-2026):** workflow `develop unit tests (no deployment)` con `permissions: contents: read`, checkout sin credenciales persistentes y Python 3.11. Run: https://github.com/masQelec/service.cloud.masqelec/actions/runs/44188131468; `Ran 233 tests in 0.359s / OK`. Esto **no** verifica ejecución en KodiELEC, dispositivos remotos, publicación GitHub MQC2 ni migración real. `main`, `cloud/master`, `cloud/develop/system.d` y montajes no se han modificado.

### Diagnóstico seguro de divergencia (solo preflight)

Para observar qué cuenta tiene un refresh diferente, sin mostrar tokens ni hashes, ejecutar exclusivamente en KodiELEC:

```bash
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/07b008db93ad524e9cbfec5b5e0e4b63704fe15e/service.cloud.masqelec/tools/rclone_two_mount_real_probe_lab.py' -O /tmp/rclone_two_mount_real_probe_lab.py
python3 -m py_compile /tmp/rclone_two_mount_real_probe_lab.py
python3 /tmp/rclone_two_mount_real_probe_lab.py --preflight
```

En caso de discrepancia estable, salida adicional `BASELINE_REFRESH_ONEDRIVE_1|2` y `BASELINE_REFRESH_DRIVE_1|2` con `SAME/DIFFERENT`, junto a `GH_BRANCH_COMMIT_STABLE=YES`. Resultado esperado de seguridad: `LAB_RESULT=BLOCKED_BASELINE_DIVERGED`, **no** PASS. Si cambia la fuente durante la lectura: `INCONCLUSIVE_*`. No usar `--real-probe`; no copiar ni publicar ninguno de los tokens. **No se ha ejecutado todavía este script actualizado en el KodiELEC real.** Pruebas de laboratorio GitHub Actions: **239/239 OK** (run `44191814025`). [Informe completo](PREFLIGHT_BASELINE_DIVERGENCE_2026-11-17.md).

## 8. Resultado real del segundo preflight

El operador comunicó `ONEDRIVE_1=DIFFERENT`, `ONEDRIVE_2=DIFFERENT`, `DRIVE_1=SAME`, `DRIVE_2=SAME` en etiquetas `BASELINE_REFRESH_*`, `GH_BRANCH_COMMIT_STABLE=YES`, `LIVE_CONFIG_CHANGED=NO`, `LAB_RESULT=BLOCKED_BASELINE_DIVERGED`. El bloqueo protege frente a una sobrescritura sin evidencia de validez OAuth. **No repetir el preflight sin una nueva pregunta diagnóstica**. No hacer `rclone lsf`, `config reconnect`, OAuth real, PUT GitHub ni cambios en montajes/unidades. Arquitectura objetivo: 2 FUSE (cada `users_library_N` crypt sobre OneDrive `library_N`) + 4 bind a las rutas Kodi originales; sin desplegar.

## 9. Gate P0-B/P0-D después del segundo preflight

## Actualización 17-11-2026: P0-B (generaciones) y P0-D (readback), laboratorio

Se incorporaron en `develop` los módulos puros `lib/rclone_two_mount_generation.py` (`5730c0e`) y `lib/rclone_two_mount_readback.py` (`d441ea5`), con **32 pruebas nuevas** sobre el baseline 239. GitHub Actions run [44194785936](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44194785936) confirma **271/271 OK**.

- P0-B: **PASS en simulación**, compara canónico, dos cuentas aisladas y MQC2 mediante huellas HMAC efímeras, SHA/HEAD y cuatro epochs. Distingue cambio local, cambio remoto y ABA **si y solo si** todos los escritores incrementan epochs fiables. No existen en el legacy; con escritores no coordinados `blocked_untracked_writers`.
- P0-D: **PASS parcial sintético**, confirma GET MQC2 autenticado y bytes idénticos, blob SHA esperado, commit HEAD leído estable. `verified_lab_only` **no es autorización**.
- P0-C: **NO IMPLEMENTADO**; múltiples CLIENTES/montajes rclone siguen pudiendo renovar refresh OneDrive. El token local renovado después del backup es la **causa confirmada por operador** del bloqueo P0-A.
- Sin red OAuth, sin GitHub PUT de credenciales, sin migración. `main`, `cloud/master`, `cloud/develop/system.d` intactos. Los dos flags siguen False.
- Documentación técnica: [OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md](OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md).


**Para reproducir pruebas sintéticas** (Ubuntu, checkout `develop`; no ejecutar código live de KodiELEC):

```bash
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

No se necesita permiso para modificar el sistema, OAuth real, GitHub token ni claves. No ejecutar pruebas con `rclone lsf`, ni editar `rclone.conf` o `system.d`.

## Estado P0-C: protocolo de flota (17-11-2026)

**Última suite CI:** **322/322 OK**, GitHub Actions [44196168382](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44196168382) (Python 3.11, sin Kodi, OAuth real, GitHub PUT ni mounts). Se incorporaron `rclone_two_mount_fleet.py` (commit `64ddba43`, **35 tests**) y `rclone_two_mount_fleet_gate.py` (commit `b5bf5a47`, **16 tests**). Total: **51 tests nuevos** respecto de 271. Los resultados `quiescent_lab_only`, `both_accounts_quiescent_lab_only` y `dual_fence_lab_only` **nunca autorizan publicación**.

- Impide aceptar flota declarada incompleta/no verificada, legacy activo, escritores desconocidos, equipo offline, ack ausente, ack obsoleto, epoch cambiado, cambio de membresía/revisión, expiración, reloj inválido o cohorte incoherente.
- La conjunción de ambos OneDrive + fuentes P0-B **bloquea expresamente `baseline_diverged`**, como ocurre ahora en KodiELEC tras renovación OneDrive posterior al MQC2. No se han seleccionado ni copiado tokens.
- **No hay autoridad real de inventario, attestation autenticada, fencing de procesos rclone, contador global verificable, servicio coordinador, persistencia de leases ni protocolo de reanudación tras crash.** Los booleanos y recibos de los tests son afirmaciones sintéticas; ningún usuario puede convertirlos en una garantía de exclusión.
- Microsoft documenta que al renovar un refresh token no invalida automáticamente el anterior: https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens . La divergencia confirma backup desactualizado, no prueba expiración/revocación de los tokens antiguos ni exige desconectar clientes.
- **Sigue bloqueado:** P0-A coherencia MQC2; P0-C operativo; P0-D PUT/readback real; despliegue P0-E/H. Flags `RCLONE_TOKEN_SYNC_ENABLED=False`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; `cloud/develop/system.d`, `addon/main` y `cloud/master` sin cambios.
- Guía completa: [OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md](OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md).


Para ejecutar únicamente los tests sintéticos en un checkout limpio de Ubuntu:

```bash
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

No usar pruebas OAuth en proveedores ni unit tests en una máquina de producción que tenga su configuración real montada. El software no tiene todavía mecanismo de congelación/ACK para clientes reales.


## Aclaración de arquitectura y actualización del addon (17-11-2026)

El operador confirma: MASTER publica el catálogo de biblioteca, los CLIENTES ya reciben versiones del addon y el servicio arranca con el código actualizado. Los .strm apuntan a las **cuatro rutas Kodi existentes** y no requieren que el CLIENTE haga barridos de directorios OneDrive para descubrir archivos. La migración se hace **localmente en el arranque de cada versión definitiva**: leer/preservar credenciales locales, preparar los dos snapshots crypt→OneDrive, y sustituir 4 FUSE por 2 FUSE+4 bind únicamente al tener pruebas de idoneidad y rollback. **No hace falta un coordinador central** para esa migración; la sincronización OAuth entre dispositivos es independiente y sigue bloqueada. El addon todavía no ejecuta el cutover. Ver [ADDON_STARTUP_ROLLOUT_2026-11-17.md](ADDON_STARTUP_ROLLOUT_2026-11-17.md). `startup_decision()` es política pura, no ejecución; GitHub Actions **352/352 OK** (run 44197364926).

El código nuevo `startup_decision()` no realiza comprobaciones reales ni instalaciones. No ejecutarlo como si activara el esquema; cada una de las condiciones (conf local válido, runtime, Kodi libre, rollback) debe implementarse con verificaciones del dispositivo antes del cutover.

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

**Comando exacto del preflight — no monta nada:**

```bash
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/17963e287152afe1cb845f73d460cdfd53b81091/service.cloud.masqelec/tools/rclone_two_mount_fuse_bind_local_lab.py' -O /tmp/rclone_two_mount_fuse_bind_local_lab.py
python3 -m py_compile /tmp/rclone_two_mount_fuse_bind_local_lab.py
python3 /tmp/rclone_two_mount_fuse_bind_local_lab.py --preflight
```

No ejecutar `--run-local-pilot` sin conocer sus efectos temporales y el procedimiento de limpieza. La ejecución real no está registrada como PASS.

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


## Laboratorio systemd aislado preparado (18-11-2026; NO ejecutado en KodiELEC)

Nuevo script **autocontenido** `tools/rclone_two_mount_systemd_local_lab.py`: preflight exclusivamente lectura; tras confirmación explícita, seis unidades con nombres aleatorios solo en `/run/systemd/system` y dos FUSE + cuatro bind usando fixtures locales solo en `/tmp/masqelec-sd-lab-<16hex>`. Verifica Type=simple, BindsTo/After y bind oneshot con montajes reales, lectura, parada inversa y limpieza obligatoria. No enable, no acceso OAuth, no cambio de rutas Kodi ni servicios legacy; sí realiza `systemctl daemon-reload` global, sin reiniciar servicios. Bloquea un nuevo ensayo si quedan residuos del anterior. **617/617 tests CI PASS** [44391899556](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44391899556), pero NO demuestran systemd/FUSE real en KodiELEC. [Runbook y comandos](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md). Esperar resultado `READY_FOR_ISOLATED_SYSTEMD` del preflight antes de ejecutar el piloto. Flags de migración siguen `False`.

### 18/11/2026 — inventario OAuth local de flota, sin tokens ni tráfico

Nuevo script `tools/rclone_two_mount_fleet_inventory.py` en `addon/develop`, solo `--inventory`, requiere root. Lee `/proc/PID/comm` y **cmdline local sin imprimirla**, cuenta rclone mount/otros y examina `mountinfo` para cuatro rutas legacy y dos raíces v2; no abre configuraciones, no hace llamadas remotas ni cambia systemd. Cualquier lectura incompleta bloquea. **La captura local NO confirma coordinación de otros dispositivos y NUNCA permite sondeo OAuth**, aunque reporte cero procesos. Ejecutar primero en MASTER y después en cada CLIENTE conocido. [Procedimiento](FLEET_OAUTH_INVENTORY_2026-11-18.md). No desactivar el bloqueo de `--real-probe` ni reiniciar servicios por estos números.

### 19/11/2026 — primer arranque automático y retirada systemd legacy (CÓDIGO LISTO EN DEVELOP, DESACTIVADO)

Se ha conectado `rclone_two_mount_autostart.tick` al primer arranque de `service.py` y a un trabajador periódico (60 s), para postergar la migración mientras Kodi reproduzca y reintentar con `Player.GetActivePlayers == []`. Llama al adaptador transaccional ya existente bajo flags de release y a `rclone_two_mount_legacy_cleanup.py` SOLO después de `ACTIVE`; la limpieza conserva journal privado y retira únicamente los cuatro `.service` legacy byte-idénticos, con reanudación tras apagón. Se ha corregido la detección `systemctl is-enabled`: un resultado no cero no basta; se exige salida `disabled` o `not-found` (solo para archivos ya ausentes). `cloud_storage.py` ya bloquea la reinstalación legacy si el modo es `active` o `unsafe`.

**754/754 CI PASS** [Actions 44424953101](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44424953101). Los 5 flags de cutover/retirada/rollback/recuperación siguen **False**; rutas de medios de prueba predeterminadas **vacías**, por lo que un intento de release sin selección de medios bloquearía `BLOCKED_MEDIA_FIXTURES`. **NO ejecutado** con OAuth real ni systemd definitivo. Los STRM locales no se eliminan. [Runbook de primer arranque](AUTO_FIRST_RUN_CUTOVER_2026-11-19.md).

### 19/11/2026 — detección automática de medios de prueba por cuenta en .strm locales

Nuevo `lib/rclone_two_mount_media_samples.py`: selecciona sin red una ruta de prueba por cada cuenta OneDrive leyendo únicamente los `.strm` del catálogo local (`/storage/videos` y `/storage/tvshows`). Validación de symlinks/traversal, <=8192 bytes por archivo, recorrido acotado a 200k entradas/12 s/8 niveles y **sin imprimir rutas**. Integrado en `rclone_two_mount_autostart.tick()` cuando `RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES=()`: no precisa configuración manual por cliente. Playback ocupado difiere sin explorar; fase unsafe permite recuperar sin muestras. CLI de solo lectura `--inventory` imprime `PASS_2_LOCAL_STRM_ACCOUNTS` o bloqueo, sin tocar montajes/OneDrive. **773/773 CI PASS** ([44426001148](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44426001148)).

**AÚN PENDIENTE:** preflight físico en MASTER y CLIENTE, confirmar existencia real de los vídeos tras levantar v2, ensayo cutover+rollback/reboot. Mantener flags desactivadas. [Procedimiento y script](AUTO_FIRST_RUN_CUTOVER_2026-11-19.md).
