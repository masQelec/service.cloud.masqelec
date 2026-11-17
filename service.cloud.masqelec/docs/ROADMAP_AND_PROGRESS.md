# Registro de progreso, decisiones y próximos gates

**Corte comprobado:** 17-11-2026. Los resultados de KodiELEC y Ubuntu que figuran como PASS proceden de la salida comunicada por el operador. Los commits se han verificado en GitHub; los cambios de documentación posteriores no constituyen nuevas pruebas de código.

## 1. Estado ejecutivo

**Objetivo:** mantener un MASTER masQelec que publique respaldos OAuth MQC2 compatibles con CLIENTES legacy y futuros CLIENTES v2, reduciendo cada dispositivo de 4 a 2 procesos rclone y conservando las cuatro rutas de Kodi.

**Estado:** arquitectura y políticas preparadas en `develop`; **no desplegadas**. Los cuatro montajes legacy siguen como referencia operativa. La suite reportada es **228/228 OK**. **Siguiente hito:** `--preflight` real de SHA GitHub + MQC2, **sin** sondeo Microsoft.

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

**Gates actualizados:** tests adicionales = 5, **NOT RUN**; suite histórica = 228/228 PASS; preflight KodiELEC = **NOT RUN**; publicación OAuth v2 = **NO**; montaje FUSE/bind real = **NOT RUN**. El siguiente paso sigue siendo ejecutar la suite ampliada en Ubuntu y el `--preflight` fijado a `c701e74e` en KodiELEC. El retorno `BLOCKED_FLEET_COORDINATION` de `--real-probe` es intencional. Los gates P0-B/P0-C/P0-D y migración aún no están resueltos.
