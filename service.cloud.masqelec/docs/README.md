# Documentación técnica — `service.cloud.masqelec`

**Índice de referencia para desarrolladores y nuevos chats.** Estado cerrado a 17-11-2026; 228 pruebas unitarias **OK** según salida comunicada por el operador. Las propuestas de OAuth v2 y dos montajes FUSE permanecen **sin desplegar**.

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
