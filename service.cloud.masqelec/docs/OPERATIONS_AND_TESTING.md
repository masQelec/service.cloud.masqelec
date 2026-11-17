# Operaciones, pruebas y diagnóstico — masQelec

**Ámbito:** pruebas sin corte de reproducción. Suite CI actual de `develop`: **271/271 OK** (GitHub Actions run 44194785936). El preflight real quedó BLOCKED por refresh OneDrive divergentes tras renovación rclone confirmada. P0-B/P0-D: laboratorios, **no** despliegue ni sincronización.

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
