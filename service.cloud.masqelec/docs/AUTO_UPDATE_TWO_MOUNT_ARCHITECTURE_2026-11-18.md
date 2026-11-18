# Arquitectura acordada: actualización automática del addon, migración local y recuperación OAuth bajo demanda

**Decisión técnica del usuario — 18/11/2026. Solo documentación; SIN ACTIVAR, DESPLEGAR NI PUBLICAR una nueva versión.**

## Objetivo real de distribución (NO migración gradual manual)

- Todos los dispositivos KodiELEC tienen instalado `service.cloud.masqelec` y reciben versiones nuevas mediante la actualización normal desde el repositorio de addons del usuario. **La entrega de código es responsabilidad del repositorio de actualizaciones de Kodi**, no del contenido de `cloud.masqelec`.
- La misma release final instalará la lógica **dos raíces FUSE + cuatro bind**, sin cambiar los cuatro destinos históricos `/storage/.mnt/{videos,tvshows}/{1,2}`, en MASTER y CLIENTES. El proceso por dispositivo debe ser **autónomo, idempotente, seguro ante cortes e independiente** del estado de los demás. No se exige que todos estén conectados ni migrarlos manualmente uno por uno.
- Las instalaciones no suceden a la vez: Kodi comprueba periódicamente actualizaciones y algunos equipos pueden estar apagados, sin Internet o con actualizaciones desactivadas. No existe una transición global atómica. La **convivencia de legacy y v2** no es una fase opcional, sino una condición obligatoria de compatibilidad.
- El MASTER controla el catálogo y mantiene el **MQC2 cifrado publicado** en `masQelec/cloud.masqelec/rclone/rclone.conf.crypt`. **No confundir GitHub del addon con el repositorio de configuración**. El repositorio de addon instala el motor; MQC2 distribuye una reserva de credenciales tras publicación validada por MASTER.
- Un CLIENTE **mantiene sus tokens OAuth locales mientras sean válidos**. Cuando se detecte una señal inequívoca de fallo de autenticación (no simple falta de red, 429, permisos, 403 genérico ni fallo temporal), puede recuperar el MQC2 más reciente, autenticar su cifrado, verificar que corresponde a las mismas cuentas y al mismo crypt, construir solo el reemplazo OAuth de la cuenta fallida y probar el candidato. Si falla, **no sustituir tokens locales ni tocar rutas**; registrar estado y reintentar con control.
- Recuperar credenciales no debe restaurar Google Drive del MASTER ni sobrescribir indiscriminadamente el `rclone.conf` compartido. En la arquitectura nueva, **cada raíz FUSE usa su cuenta aislada**; actualizar el archivo compartido no basta. La recuperación afecta a la cuenta afectada y requiere recarga controlada del proceso que la usa; no basta con descargar un fichero.
- El MASTER debe continuar **publicando credenciales vigentes también cuando ya use dos FUSE**, reconciliando las credenciales de sus dos archivos aislados con los campos canónicos de las dos Google Drive, sin mezclar snapshots ni publicar un token solo por `expiry` o mtime. Publicación MQC2 con CAS y verificación de lectura remota. Si no puede determinar un estado coherente, NO publicar.
- Kodi puede estar reproduciendo un STRM: **no desmontar ni activar nuevas unidades durante reproducción**, posponer hasta inactividad y validar dos raíces FUSE + cuatro binds antes de levantar el bloqueo de bibliotecas.
- En reboot/corte de alimentación: estado durable, inicio fail-closed, rollback probado y protección contra unidades legacy reactivadas por systemd antes del addon. Logs sin secretos; notificar migración aplicada, diferida o recuperación manual requerida.

## Diferencias concretas entre este objetivo y el código actual

| Componente | Existe hoy en develop | Falta para release |
|---|---|---|
| `addon.xml` | `version=2.3.1`; `service.py` se inicia con Kodi | Incrementar versión, generar ZIP de addon y metadatos de repositorio Kodi; verificar actualización y ejecución efectiva en equipos |
| `rclone_two_mount_plan.py` | Genera 2 unidades FUSE y 4 bind; laboratorio systemd LOCAL KodiELEC PASS | Integrar transacción y verificar compatibilidad de unidades reales y de Kodi |
| `rclone_two_mount_startup_stage.py` | Solo prepara staged cuando flag es True; flag False | Activación **automática por dispositivo** tras instalación de versión y gates de inactividad/rollback/identidad; sin consentimiento manual por equipo |
| `rclone_two_mount_live_adapter.py` | Tiene cutover y rollback simulado; no lo llama `service.py` | Integrar cutover con bloqueo local, journal durable, validación y recuperación real tras fallo/reboot |
| `rclone_two_mount_rollout.py` | Decisiones puras; texto `operator_only` y flags False | Ajustar protocolo a activación local autónoma, verificable; no limitar a operador sin acceso a todos los clientes |
| `cloud_storage.py` | Descarga normalmente MQC2 al inicio y preserva OAuth local; el modo v2 activo bloquea el actualizador legacy | Separar **actualización ordinaria de opciones** de **adopción de tokens bajo fallo confirmado**, no reiniciar 4 unidades legacy en v2 |
| `rclone_token_sync.py` | Publicación MASTER y recuperación CLIENT legacy preparadas, `tick` apagado; se retorna temprano cuando v2 está activo | **GAP BLOQUEANTE:** implementar publicación MASTER v2 a partir de dos configs privadas y recuperación CLIENT v2 por cuenta, con su propio ciclo/estado |
| `rclone_two_mount_boot_guard.py` | Puede bloquear scans si detecta transición incompleta, al ejecutarse el addon | **No evita que systemd arranque unidades antes de Kodi**. Probar reboot y protección de arranque fuera del proceso Kodi |
| `cloud.masqelec` MQC2 | Reserva cifrada desde MASTER/compatible legacy | Consistencia y readback después del refresh, sin tratar el archivo remoto como verdad automática de salud |
| Kodi repositorio de addons | Código `develop` no se instala solo en toda la flota | Publicación efectiva de versión **por encima de 2.3.1**, metadatos repositorio, compatibilidad, tests de upgrade y downgrade |

## Modelo de control adecuado

**No** forzar un procedimiento de parada simultánea de todos los dispositivos. La documentación antigua P0-C modelaba coordinación interdispositivo para publicación global estricta; sirve como investigación del riesgo, **pero no es el modelo de distribución elegido**. La actualización del addon será autónoma por nodo, y no debemos impedirla solo porque un CLIENTE desconocido esté apagado.

**Sí** exigir: coordinación **local** de procesos rclone y archivos compartidos en cada nodo; publicación MASTER exclusiva y autenticada para MQC2; un CLIENTE que no pueda verificar el reemplazo sigue con su configuración y queda marcado como recuperación pendiente. La coexistencia de clientes legacy y v2 es compatible solo si las estructuras publicadas y las unidades antiguas siguen siendo legibles.

Microsoft explica que al intercambiar refresh tokens no se revocan automáticamente los anteriores: https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens . Esto **no prueba** que un token esté vigente ni garantiza que no sufra revocación por otras causas. No reescribir el token del CLIENTE que funciona solo porque MQC2 tiene uno diferente.

## Gates mínimos sin publicar la release todavía

1. Suite técnica de **upgrade automático por addon** desde 2.3.1, incluyendo CLIENTE apagado/offline que actualiza más tarde, compatibilidad con la versión antigua, y protección del estado ante downgrade.
2. Cutover local idempotente y seguro con Kodi reproduciendo, Kodi inactivo, reboot antes/después de desmontar, rollback OAuth y servicio systemd temprano.
3. MASTER v2 publica MQC2 de ambas cuentas aisladas de forma coherente con Google Drive y verifica CAS/readback, sin detener toda la flota.
4. CLIENTE v2 usa sus tokens primero, identifica fallo OAuth real, recupera **solo** la cuenta afectada desde MQC2, verifica candidato y recupera su montaje tras estado idle; nunca confunde 429/offline con auth.
5. Cumplir integración real con Kodi y reproducción STRM en las cuatro rutas; no lanzar despliegue mientras falten estos tests.

**Estado operativo:** `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`, `RCLONE_TWO_MOUNT_STAGING_ENABLED=False`, `RCLONE_TOKEN_SYNC_ENABLED=False`; `AUTO_UPDATE_CUTOVER_IMPLEMENTED=NO`; `V2_MASTER_PUBLISH_IMPLEMENTED=NO`; `V2_CLIENT_AUTH_RECOVERY_IMPLEMENTED=NO`; `RELEASE_AUTHORIZED=NO`. El PASS real systemd LOCAL queda confirmado y **no se necesita repetirlo**.

Este documento fija la **intención** y los requisitos; no afirma que el código ya los implemente.
