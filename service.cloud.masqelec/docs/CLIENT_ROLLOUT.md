# MASTER y CLIENTES — distribución, coexistencia y migración 2 FUSE

**Estado:** diseño + código de *staging* en `develop`. **NO** existe un actualizador automático operativo del addon para instalar esta arquitectura; no está autorizada ninguna migración de MASTER ni CLIENTES.

## 1. Tres vías de actualización: no mezclarlas

| Vía | Código actual | Qué hace / qué NO hace |
| --- | --- | --- |
| **Actualización del sistema operativo** | `lib/updater.py` + `service._update_system_wrapper` | Busca `os-release` remoto por `COREELEC_DEVICE` mediante rclone, compara `VERSION_ID`, coloca paquete en `/storage/.update` y ofrece reiniciar. **No activa automáticamente arquitectura FUSE/bind del addon.** |
| **Configuración remota/servicios LEGACY** | `lib/cloud_storage.py` | Obtiene `rclone.conf.crypt`, compara/preserva tokens compatibles, descarga `cloud/develop/system.d/` y puede ejecutar `daemon-reload`/`try-restart`. **No subir allí unidades v2 durante el piloto.** |
| **Distribución futura de esquema v2** | `lib/rclone_two_mount_rollout.py`, `lib/rclone_two_mount_plan.py` + manifiesto `rollouts/` | Reconoce modelo/versionado, prepara configs/unidades en `/tmp` privado, bloquea activación automática. **No descarga/instala una actualización funcional del addon en los CLIENTES; ese canal falta.** |

La instalación/actualización de ficheros del addon entre dispositivos requiere una vía versionada real que aún no se ha implementado ni verificado en esta fase. No presentar el manifiesto como un instalador.

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
