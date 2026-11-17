# MASTER y CLIENTES — distribución, coexistencia y migración 2 FUSE

**Estado:** el operador confirma que los CLIENTES ya reciben versiones del addon y lo inician con el código actualizado. **Este repositorio no contiene un instalador de montajes v2**, y no está autorizada ninguna migración. El futuro arranque del addon actualizado es el canal previsto, sin servidor de coordinación.

## 1. Tres vías de actualización: no mezclarlas

| Vía | Código actual | Qué hace / qué NO hace |
| --- | --- | --- |
| **Actualización del sistema operativo** | `lib/updater.py` + `service._update_system_wrapper` | Busca `os-release` remoto por `COREELEC_DEVICE` mediante rclone, compara `VERSION_ID`, coloca paquete en `/storage/.update` y ofrece reiniciar. **No activa automáticamente arquitectura FUSE/bind del addon.** |
| **Configuración remota/servicios LEGACY** | `lib/cloud_storage.py` | Obtiene `rclone.conf.crypt`, compara/preserva tokens compatibles, descarga `cloud/develop/system.d/` y puede ejecutar `daemon-reload`/`try-restart`. **No subir allí unidades v2 durante el piloto.** |
| **Distribución futura de esquema v2** | `lib/rclone_two_mount_rollout.py`, `lib/rclone_two_mount_plan.py` + manifiesto `rollouts/` | Reconoce modelo/versionado, prepara configs/unidades en `/tmp` privado, bloquea activación automática. **No descarga/instala una actualización funcional del addon en los CLIENTES; ese canal falta.** |

**Corrección aportada por el operador:** la actualización del addon en los CLIENTES ya existe y provoca el inicio de la versión nueva. No se ha auditado aquí el mecanismo de distribución, pero **no hace falta inventar uno nuevo ni tratar `updater.py` (actualización del SO) como actualizador del addon**. Lo pendiente es que la versión definitiva del addon ejecute la migración local y reversible.

## 2. Objetivo final de la transición

- MASTER + CLIENTES nuevos: **dos montajes FUSE, uno por cuenta**, y cuatro bind a las rutas existentes.
- CLIENTES sin migrar: mantienen los **cuatro FUSE legacy**.
- Misma estructura lógica **seis secciones**: 2 `crypt` + 2 OneDrive + 2 Google Drive.
- Mismo formato de reserva GitHub, `rclone/rclone.conf.crypt` autenticado MQC2; los CLIENTES antiguos no deben romperse.
- Nuevas credenciales por dispositivo: `account1.conf` y `account2.conf` **locales** y privadas, derivadas de una configuración validada. No deben publicarse en claro en `cloud/`.
- Cortes y rollback de montajes solo en dispositivo expresamente autorizado, con reproducción detenida.

## 3. Contrato de versión de la propuesta

`cloud.masqelec/develop/rollouts/rclone-two-mount/v1/manifest.json` contiene únicamente metadatos: esquema 1, `two-fuse-v1`, `candidate_id=2026-11-17-two-fuse-v1`, cuatro rutas Kodi y precondiciones. Declara:

```json
{
  "schema": 1,
  "layout": "two-fuse-v1",
  "candidate_id": "2026-11-17-two-fuse-v1",
  "activation": "operator_only",
  "update_mode": "stage_only",
  "auto_apply": false,
  "production_authorized": false
}
```

Esto es **un extracto explicativo**, no el fichero completo ni una autorización. El manifiesto completo puede añadir campos. En `develop`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; no cambiarlo como parte de la documentación.

El marcador local reservado por dispositivo está definido en `rclone_two_mount_rollout.py`; no lo crear a mano. `legacy` y `prepared` siguen con servicios antiguos; `active` bloqueará el actualizador legacy; `unsafe` exige intervención. El código preparado impide que un CLIENTE `active` vuelva a descargar unidades legacy silenciosamente.

## 4. Protocolo de distribución que hay que implementar

| Fase | Estado requerido | Garantías antes de avanzar |
| --- | --- | --- |
| **A. Descubrir** | `legacy` | Detectar versión local del addon, capacidades rclone/systemd y elegibilidad. |
| **B. Descargar** | `legacy` | Obtener paquete del addon v2 y manifiesto versionado desde origen autorizado. Validar procedencia, integridad, tamaño y compatibilidad; sin activación. |
| **C. Preparar** | `prepared` solo cuando exista código autorizado | Generar dos configs privadas con `crypt` original; construir unidades en staging, no en `system.d`; comprobar respaldos/espacio. |
| **D. Verificar** | `prepared` | Tests/sondeos controlados, prueba de rutas alternativas, versión `Type=notify`, tokens y montaje. NO solicitar OAuth real si hay escritores activos. |
| **E. Autorizar** | `prepared` | Operador identifica equipo, ventana sin reproducción, snapshot de configuración/unidades y rollback ensayado. |
| **F. Activar** | `active` solo tras éxito | Orquestación transaccional por dispositivo: detener legacy de forma controlada, activar dos FUSE y cuatro bind, comprobar rutas y Kodi. La implementación **no existe** hoy. |
| **G. Confirmar** | `active` | Lectura, biblioteca, reproducciones, reconexión, reinicio, reintento y conservación de tokens. |
| **H. Revertir** | fallo/solicitud explícita | Quitar bind nuevos, detener nuevos FUSE, restaurar respaldos legacy, activar cuatro servicios; comprobar Kodi. No reescribir tokens sin validación. |

Durante B/C/D, **prohibidos** `try-restart`, `stop`, `mount --bind` sobre rutas vivas y modificaciones de `cloud/system.d`.

### Condiciones de autorización de un CLIENTE

1. Compatibilidad de binario rclone y dependencias systemd verificada en **ese equipo**.
2. Dos OneDrive + wrappers `crypt` conservados con nombres originales.
3. Google Drive sigue disponible para actualizaciones/logs.
4. Verificación de montajes en rutas alternativas sin FUSE o rutas Kodi ocupadas.
5. Sin reproducción activa (incluye procesos que mantengan archivos abiertos).
6. Prueba de rollback sin pérdida de credenciales ni de datos; copia de unidades legacy.
7. Sistema de recuperación/reconciliación OAuth v2 **operativo y validado**.
8. Autorización específica del operador; no basta un indicador remoto.

## 5. Convivencia de CLIENTES antiguos y nuevos

La reducción a **un escritor por cuenta por dispositivo** no significa un único refresh token global. Diferentes CLIENTES pueden renovar la misma cuenta. No se debe subir automáticamente el refresh de un CLIENTE como si fuese la versión más reciente.

Política v2 preparada, pero inactiva:

- El MASTER compara las dos instantáneas OAuth privadas con el archivo canónico y la reserva MQC2.
- Conserva dos Google Drive y dos `crypt`; solo contempla cambios OneDrive verificados.
- El cliente v2 puede preparar una recuperación de una cuenta ante AUTH explícito; no instalarla mientras el montaje esté escribiendo.
- El SHA remoto de GitHub evita reintentos ciegos sobre el mismo blob; **no** prueba cuál refresh es el correcto.
- CLIENTES antiguos requieren seguir recibiendo el formato canónico `rclone.conf.crypt` hasta que se completen sus migraciones.

**Gap bloqueante:** no existe todavía coordinación global de sesiones/rotaciones entre todos los CLIENTES. Los dos nuevos procesos por equipo no resuelven esa sincronización por sí solos.

## 6. Actualización del paquete una vez se active un CLIENTE v2

El diseño de seguridad debe evitar un `try-restart` del nuevo rclone por actualizar una unidad. Las actualizaciones del addon deben distinguir:

- **Cambios de código**: distribuir versión, tests previos, conservación del estado local.
- **Cambios de unidad**: staging y comparación, aplicar solo en ventana o tras validación; nunca asumir que un reinicio es inocuo.
- **Cambios de token**: coordinación específica y validación, no sobrescritura por fecha.
- **Cambios de esquema**: migración por dispositivo, reversible.
- **Actualización de sistema operativo**: flujo `updater.py` ya existente, independiente.

Todo paquete futuro debe identificar su versión y compatibilidad con marcadores más antiguos. Si el addon retrocede de versión, no debe arrancar los cuatro servicios legacy por interpretar `active` como inexistente.

## 7. Riesgos y pruebas pendientes

**P0**: canal real de distribución segura del código del addon; persistencia/recuperación del marcador; activación idempotente y rollback; concurrencia OAuth entre equipos; FUSE/bind reales; `Type=notify`; arranque de Kodi y fallos de red. **P1**: observabilidad de versiones/estados, flota parcial, métricas de rendimiento y ventanas de actualización.

No se han ejecutado operaciones de esta migración en CLIENTES reales. Los laboratorios anteriores solo generan propuestas privadas.

Documentación asociada: [ARCHITECTURE_AND_MODES.md](ARCHITECTURE_AND_MODES.md), [OPERATIONS_AND_TESTING.md](OPERATIONS_AND_TESTING.md), [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

## Estado P0-C: protocolo de flota (17-11-2026)

**Última suite CI:** **322/322 OK**, GitHub Actions [44196168382](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44196168382) (Python 3.11, sin Kodi, OAuth real, GitHub PUT ni mounts). Se incorporaron `rclone_two_mount_fleet.py` (commit `64ddba43`, **35 tests**) y `rclone_two_mount_fleet_gate.py` (commit `b5bf5a47`, **16 tests**). Total: **51 tests nuevos** respecto de 271. Los resultados `quiescent_lab_only`, `both_accounts_quiescent_lab_only` y `dual_fence_lab_only` **nunca autorizan publicación**.

- Impide aceptar flota declarada incompleta/no verificada, legacy activo, escritores desconocidos, equipo offline, ack ausente, ack obsoleto, epoch cambiado, cambio de membresía/revisión, expiración, reloj inválido o cohorte incoherente.
- La conjunción de ambos OneDrive + fuentes P0-B **bloquea expresamente `baseline_diverged`**, como ocurre ahora en KodiELEC tras renovación OneDrive posterior al MQC2. No se han seleccionado ni copiado tokens.
- **No hay autoridad real de inventario, attestation autenticada, fencing de procesos rclone, contador global verificable, servicio coordinador, persistencia de leases ni protocolo de reanudación tras crash.** Los booleanos y recibos de los tests son afirmaciones sintéticas; ningún usuario puede convertirlos en una garantía de exclusión.
- Microsoft documenta que al renovar un refresh token no invalida automáticamente el anterior: https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens . La divergencia confirma backup desactualizado, no prueba expiración/revocación de los tokens antiguos ni exige desconectar clientes.
- **Sigue bloqueado:** P0-A coherencia MQC2; P0-C operativo; P0-D PUT/readback real; despliegue P0-E/H. Flags `RCLONE_TOKEN_SYNC_ENABLED=False`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; `cloud/develop/system.d`, `addon/main` y `cloud/master` sin cambios.
- Guía completa: [OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md](OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md).


El rollout v2 no puede convertir un cliente legacy en escritor cooperativo solo mediante un cambio de marcador. `cloud/develop/system.d/` conserva 4 unidades legacy y no debe tocarse; cualquier instalación de coordinación requiere enrolamiento auténtico, pruebas en rutas alternativas y autorización por dispositivo. La migración 2 FUSE+4 bind no es un reemplazo de la coordinación entre equipos.


## Aclaración de arquitectura y actualización del addon (17-11-2026)

El operador confirma: MASTER publica el catálogo de biblioteca, los CLIENTES ya reciben versiones del addon y el servicio arranca con el código actualizado. Los .strm apuntan a las **cuatro rutas Kodi existentes** y no requieren que el CLIENTE haga barridos de directorios OneDrive para descubrir archivos. La migración se hace **localmente en el arranque de cada versión definitiva**: leer/preservar credenciales locales, preparar los dos snapshots crypt→OneDrive, y sustituir 4 FUSE por 2 FUSE+4 bind únicamente al tener pruebas de idoneidad y rollback. **No hace falta un coordinador central** para esa migración; la sincronización OAuth entre dispositivos es independiente y sigue bloqueada. El addon todavía no ejecuta el cutover. Ver [ADDON_STARTUP_ROLLOUT_2026-11-17.md](ADDON_STARTUP_ROLLOUT_2026-11-17.md). `startup_decision()` es política pura, no ejecución; GitHub Actions **352/352 OK** (run 44197364926).
