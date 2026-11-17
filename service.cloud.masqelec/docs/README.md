# Documentación técnica — `service.cloud.masqelec`

**Índice para desarrolladores y nuevos chats.** Última suite CI confirmada: **352/352 OK** (17-11-2026). P0-B generaciones/ABA, P0-C simulación de flota y P0-D readback: laboratorios sin instalación; preflight real con ambas OneDrive divergentes tras renovación rclone comunicada por el operador. OAuth v2 y 2 FUSE + 4 bind **sin desplegar**.

## Documentación mantenida (fuente de trabajo)

| Documento | Cuándo consultarlo |
| --- | --- |
| [README principal](../../README.md) | Qué hace el addon, instalación conceptual, status y reglas básicas |
| [Arquitectura, MASTER/CLIENT y LEGACY/v2](ARCHITECTURE_AND_MODES.md) | Diagrama de procesos, roles, ficheros, rutas y cifrado |
| [Operaciones, pruebas y gates](OPERATIONS_AND_TESTING.md) | Comandos seguros Ubuntu/KodiELEC, matriz PASS/PENDING y resolución de errores |
| [Seguridad y auditoría](SECURITY_AUDIT.md) | Amenazas, hallazgos, mitigaciones, evidencia, riesgos sin resolver |
| [CLIENTES: actualizaciones y migración](CLIENT_ROLLOUT.md) | Coexistencia, manifiesto, `prepared/active/unsafe`, rollback y funciones aún inexistentes |
| [Progreso, decisiones y hoja de ruta](ROADMAP_AND_PROGRESS.md) | Cambios confirmados, criterios de terminado y siguiente prioridad |
| [**Handoff 17-11-2026**](HANDOFF_2026-11-17.md) | Resumen reproducible para retomar desde otro chat; contiene comando del preflight pendiente |
| [Generaciones OAuth + CAS/readback (P0-B/P0-D)](OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md) | Prototipos puros, 271/271 PASS, garantías, límites e integración pendiente |
| [Coordinación OAuth entre MASTER y CLIENTES (P0-C)](OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md) | Flota sintética, 322/322 PASS, riesgos de legacy y opciones de arquitectura |

| [Diagnóstico divergencia real OneDrive](PREFLIGHT_BASELINE_DIVERGENCE_2026-11-17.md) | Evidencia de KodiELEC, causa confirmada y bloqueo de recuperación |
| [Actualización del addon y migración local](ADDON_STARTUP_ROLLOUT_2026-11-17.md) | Flujo real MASTER/CLIENTES, STRM, 2 FUSE+4 bind, fases y pruebas |

## Historial de laboratorios (fotos del progreso, no instrucciones de despliegue)

Estas notas se conservan para reconstruir las decisiones y problemas encontrados. **Pueden mencionar una suite o un gate que en ese momento aún estaban pendientes y que hoy ya pasaron.** Ante discrepancias, usar los documentos mantenidos y el código de `develop`.

| Informe | Qué documenta |
| --- | --- |
| [OAuth cuatro remotos](OAUTH_FOUR_REMOTES_DEVELOP_2026-11-17.md) | Inventario 2 OneDrive/2 Drive, seis secciones, riesgos iniciales, guardas del config compartido |
| [Aislamiento OneDrive/`crypt`](ONEDRIVE_MOUNT_ISOLATION_LAB_2026-11-17.md) | Diagnósticos reales, rutas `crypt→OneDrive`, validaciones y ensayos |
| [2 FUSE + 4 bind y CLIENTES](TWO_FUSE_FOUR_BIND_CLIENT_ROLLOUT_2026-11-17.md) | Generador, propuesta de systemd, versión remota no operativa |
| [Reconciliación OAuth v2](TWO_MOUNT_OAUTH_COORDINATION_2026-11-17.md) | Política pura y compatibilidad del respaldo MQC2 con CLIENTES antiguos |
| [OAuth probe real y CAS GitHub](TWO_MOUNT_OAUTH_REAL_PROBE_AND_CAS_2026-11-17.md) | SHA del blob, error 409, sondeo en copia, fence contra montajes vivos |

## Reglas de mantenimiento documental

1. **No borrar evidencia histórica**; corregirla con anotación fechada y agregar entrada al progreso. No sobrescribir un resultado FAIL con un PASS sin conservar la causa.
2. Registrar quién ejecutó cada prueba, entorno (Ubuntu/KodiELEC), rama+commit, flags, si hubo red/escritura, y salida anonimizada.
3. Mantener **PASS confirmado** separado de **esperado**, **simulado**, **no ejecutado** y **bloqueado**.
4. Después de cada lote, actualizar `ROADMAP_AND_PROGRESS.md` y el handoff o crear uno nuevo con fecha.
5. No añadir a documentación secretos, tokens, hashes de tokens, contenido de `rclone.conf` ni valores `crypt`. Usar etiquetas `account1/account2` y rutas no sensibles.
6. No activar ni sugerir migración productiva basándose en el README; se necesita un gate de release independiente y explícito.

## Estado invariante de este corte

```text
Branch de implementación:  addon/develop
Branch estable:             addon/main (sin cambios)
Cloud config de desarrollo: cloud/develop (sin cambio de system.d)
Cloud config estable:       cloud/master (sin cambios)
RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
Última suite confirmada:    228/228 OK
Próxima prueba:             tools/rclone_two_mount_real_probe_lab.py --preflight
Prueba OAuth --real-probe:  NO AUTORIZADA con montajes activos
Migración MASTER/CLIENTES:  NO DEPLOY
```

**Estado más reciente:** P0-B/P0-D son laboratorios; P0-C/P0-E–H y el preflight coherente siguen bloqueados. Las secciones históricas 228/228 y «preflight pendiente» describen el corte inicial, no el estado vivo. Consultar los apartados finales del handoff.


## Aclaración de arquitectura y actualización del addon (17-11-2026)

El operador confirma: MASTER publica el catálogo de biblioteca, los CLIENTES ya reciben versiones del addon y el servicio arranca con el código actualizado. Los .strm apuntan a las **cuatro rutas Kodi existentes** y no requieren que el CLIENTE haga barridos de directorios OneDrive para descubrir archivos. La migración se hace **localmente en el arranque de cada versión definitiva**: leer/preservar credenciales locales, preparar los dos snapshots crypt→OneDrive, y sustituir 4 FUSE por 2 FUSE+4 bind únicamente al tener pruebas de idoneidad y rollback. **No hace falta un coordinador central** para esa migración; la sincronización OAuth entre dispositivos es independiente y sigue bloqueada. El addon todavía no ejecuta el cutover. Ver [ADDON_STARTUP_ROLLOUT_2026-11-17.md](ADDON_STARTUP_ROLLOUT_2026-11-17.md). `startup_decision()` es política pura, no ejecución; GitHub Actions **352/352 OK** (run 44197364926).
