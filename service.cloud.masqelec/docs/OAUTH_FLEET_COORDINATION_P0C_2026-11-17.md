# Cloud masQelec — P0-C: coordinación OAuth entre MASTER y CLIENTES

**Fecha:** 17-11-2026 · **Estado:** PASS de lógica pura en GitHub Actions; **BLOCKED para operar en KodiELEC** · **Rama:** addon `develop`.

## 1. Hechos confirmados

- El operador verificó en KodiELEC un MQC2 con SHA/autenticidad e identidad estática correctos.
- Comparación de `refresh_token`: OneDrive `library_1` y `library_2` **DIFFERENT** respecto de MQC2; ambas Google Drive **SAME**. El operador confirmó que rclone renovó OneDrive después de publicar el backup.
- OneDrive `library_1` soporta el wrapper `crypt` `users_library_1`; OneDrive `library_2` → `users_library_2`. **No confundir los dos tipos de remoto.**
- Hoy las cuatro unidades legacy ejecutan cuatro `rclone mount` contra una configuración compartida. La alternativa prevista sigue siendo **dos FUSE** (uno por wrapper) y **cuatro bind mounts** a las rutas Kodi antiguas, todavía sin desplegar.

### Interpretación correcta de Microsoft

Microsoft indica oficialmente que la renovación de un `refresh_token` **no revoca automáticamente el anterior** (https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens). Los tokens viejos pueden dejar de funcionar por expiración o revocación independiente, pero el cambio por sí solo no demuestra invalidez. No usar la discrepancia ni la fecha del commit MQC2 para marcar CLIENTES como rotos. Igualmente, un token viejo que hoy funcione no es garantía de validez indefinida.

**Riesgos diferenciados:** (a) pérdida de actualizaciones por escritores concurrentes sobre ficheros; (b) backup MQC2 desfasado y recuperación equivocada; (c) revocación/expiración real; (d) despliegue accidental de unidades. No confundirlos.

## 2. Módulos nuevos (NO integrados en service.py)

| Fichero | Garantía estrictamente sintética |
| --- | --- |
| `lib/rclone_two_mount_fleet.py` | Modela inventario/cohorte, per-account freezes y recibos; bloquea escritores legacy, desconocidos, desconectados, sin ack, sin refresh-fence, caducados o con generación alterada. |
| `tests/test_rclone_two_mount_fleet.py` | **35 tests** de flota incompleta, concurrencia, ABA, reincorporación tardía, revocación de ventana, epochs y dos OneDrive. |
| `lib/rclone_two_mount_fleet_gate.py` | Conjunción puramente funcional entre las dos ventanas P0-C y la captura P0-B del canónico + dos cuentas + MQC2. `baseline_diverged` bloquea incluso con todos los ACK. |
| `tests/test_rclone_two_mount_fleet_gate.py` | **16 tests** para fuentes cambiantes, falta de una cuenta, falso inventario, conflicto de cohorte, deriva de HEAD/Git, expiración y divergencia. |

**Pruebas:** GitHub Actions run [44196168382](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44196168382) → `Ran 322 tests ... OK` (51 pruebas nuevas sobre 271). Estos tests son Python 3.11 con fixtures falsos. **No se ha probado protocolo real entre dispositivos**.

### ¿Qué demuestra, y qué no?

El estado `both_accounts_quiescent_lab_only` significa que, en una simulación, cada miembro declarado cooperativo aportó un ACK compatible con una cohorte y no se observaron cambios de generación en los datos sintéticos. **No significa que el proceso rclone real haya detenido OAuth.** Declarar `report_authenticated=True` o `inventory_authoritative=True` en Python no autentica dispositivos ni frena refrescos Microsoft. Los locks de Python no son locks rclone; tampoco un TTL evita que un escritor desconectado siga trabajando.

El resultado compuesto `dual_fence_lab_only` exige además P0-B sin cambios. Si el canónico difiere del MQC2 (estado real del MASTER), devuelve `blocked_published_baseline_diverged` y no selecciona token local/remoto. No hay red, escrituras de `rclone.conf`, publicación CAS, instalación o `systemctl`.

## 3. Contrato de coordinación necesario antes de producción

1. **Descubrimiento autentificado de todos los escritores OAuth**, MASTER y todos los CLIENTES, incluidos los dispositivos offline que siguen siendo capaces de volver a conectarse. Debe existir un registro estable con revisión y garantías de integridad. La mera ausencia de latido NO significa escritor parado.
2. **Control efectivo del escritor:** el proceso rclone que renueva tokens ha de respetar el fencing o quedar fuera de la sección crítica. Ningún informe de Python puede interceptar una renovación desde un montaje legacy existente. El escritor viejo que reaparece no debe poder ignorar su epoch.
3. **Alcance por cuenta:** OneDrive 1 y OneDrive 2 deben tener generaciones separadas. Publicar un MQC2 que contiene ambas exige una cohorte común, revalidación de ambas fuentes y compatibilidad con los dos Google Drive y `crypt`.
4. **Recibos y desafío verificables:** la identidad del cliente, la ventana de coordinación, el epoch y la condición de escritor parado/controlado deben estar ligados a una autenticación real; reinicios y desconexiones invalidan la ventana.
5. **Crash recovery y persistencia:** épocas/términos monotónicos recuperables, rechazo de respuestas tardías y no reasignar automáticamente un recurso por vencimiento del lease. El tiempo solo limita cuánto dura un intento, no prueba que el antiguo escritor murió.
6. **CAS y relectura independiente:** preparar candidato en copia aislada, obtener MQC2 autenticado, verificar todas las fuentes, PUT con SHA único y NO retry 409/422, GET del commit publicado y HEAD estable, validar bytes descifrados y revalidar generaciones de la flota. Toda ambigüedad → BLOCKED.
7. **Operación y rollback:** autorización explícita, rutas de ensayo, ninguna reproducción activa afectada, procedimiento de reversión y supervisión. No tocar `cloud/develop/system.d/` por riesgo de actualización de unidades en arranque.

## 4. Dos opciones de arquitectura para revisar

**Opción A — Coordinador central y un único propietario lógico por cuenta.** Requiere que **todos** los procesos autorizados participen o que se pueda suspender de forma segura cualquier escritor legacy. Solo es viable si se puede demostrar exclusión REAL del escritor rclone durante la publicación; usar `flock` solo desde el addon no basta.

**Opción B — Credenciales OAuth independientes por dispositivo.** Cada CLIENTE obtiene y mantiene su propio grant/token OneDrive, sin copiar continuamente los refresh del MASTER. Potencialmente reduce el problema de compartir estados de refresh entre dispositivos, pero exige confirmar compatibilidad de tipo de cuenta OneDrive/rclone, mecanismo de enrolamiento seguro, recuperación y continuidad con el MQC2 legacy de seis secciones. **No implementada ni demostrada**; no reautorizar cuentas de producción por una hipótesis.

**Decisión actual:** mantener ambas en evaluación. Diseñar primero inventario de escritores *solo lectura*, sin requests OAuth. La transición 2 FUSE + 4 bind por equipo es independiente y conserva el objetivo.

## 5. Matriz de seguridad/estado

| Gate | Estado |
| --- | --- |
| Preflight MQC2 real, autenticidad/identidad estática | PASS |
| Coherencia refresh del backup OneDrive | **BLOCKED** (dos divergencias conocidas) |
| P0-B generaciones/fuentes con epochs cooperativos | PASS sintético / operativo BLOCKED |
| P0-C inventario/freeze/ACK/composición | **322/322 suite PASS**, coordinación real NOT IMPLEMENTED |
| P0-D CAS/readback | PASS sintético / HTTP live NOT RUN |
| Probar OAuth contra Microsoft | **NO AUTORIZADO**, puede cambiar estado remoto |
| Montajes FUSE y bind reales | NOT RUN |
| Actualización automática de CLIENTES legacy | NOT IMPLEMENTED |
| Deploy/cambios de producción | NO |

Comando para pruebas en checkout de desarrollo (sin OAuth ni red):

```bash
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

**Siguiente entrega P0-C2:** inventario no invasivo de escritores/servicios por dispositivo + diseño de prueba de verdad para coordinar una flota aislada. No crear todavía un servicio de autorización remota ni un instalador.

## 6. Restricciones vigentes

```text
RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
P0C_OPERATIONAL_COORDINATOR=NOT_IMPLEMENTED
P0C_LIVE_TOKEN_WRITE=NO
P0C_LIVE_OAUTH_REQUEST=NO
P0C_REMOTE_GITHUB_PUT=NO
P0C_SYSTEMD_CHANGED=NO
P0C_TWO_MOUNT_DEPLOYED=NO
```

Los dos primeros flags son los existentes en código; el resto son marcadores de auditoría. No introducir tokens, claves MQC2, hashes de credenciales, contenido de `rclone.conf` o rutas con credenciales en commits ni logs.
