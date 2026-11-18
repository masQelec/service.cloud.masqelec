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

## 19/11/2026 — Decisión final: archivo MQC2 separado para addon v2 y limpieza legacy tras el primer arranque

**Responsabilidades:** el operador publica el ZIP del addon y garantiza la distribución mediante su repositorio Kodi. No asumir tarea de publicación del ZIP por parte del desarrollador. El **addon actualizado**, en el primer arranque de cada KodiELEC, debe llevar a cabo la transición local de 4 FUSE a 2 FUSE + 4 bind (mismas rutas Kodi). No es una migración manual equipo por equipo.

### Dos rutas remotas independientes

| Destinatario | Archivo en `masQelec/cloud.masqelec` rama `develop` | Estado |
| --- | --- | --- |
| Addon legacy | `rclone/rclone.conf.crypt` | EXISTE, no modificar/borrar en esta fase |
| Addon nuevo v2 | `rclone/rclone-v2.conf.crypt` | RUTA RESERVADA, NO PUBLICADO todavía |

`lib/rclone_two_mount_config_routes.py` es el **selector puro** de rutas implementado y probado: `legacy` y `prepared` eligen el nombre original, `active` elige el v2. Un estado `unsafe` o transitorio no cae silenciosamente al archivo antiguo. La separación es de **distribución de credenciales**, no implica tener simultáneamente dos arquitecturas de FUSE montadas en un dispositivo.

El formato v2 inicialmente puede mantener el **cifrado/autenticación MQC2** y la estructura canónica necesaria para validar identidades y componer un candidato por cuenta; el MASTER debe ensamblar la configuración a partir de los **dos account*.conf actualizados por rclone** y preservar los ajustes/identidades de crypt y las dos cuentas Google Drive, sin publicar snapshots mezclados. El CLIENTE consulta `rclone-v2.conf.crypt` solo cuando detecta un error OAuth inequívoco, lo descifra y valida, y recupera únicamente su cuenta afectada; no sobrescribe una cuenta sana, ni la configuración compartida de Google Drive. La simple discrepancia de refresh no equivale a fallo.

**Puntos críticos:** la nueva ruta **no existe aún en el repo cloud**; tampoco hay escritor MASTER v2 ni lector/recuperador CLIENTE v2 conectado a `service.py`. Se requiere publicación autenticada, CAS por ruta y readback; las dos publicaciones **NO** son una transacción GitHub atómica. No afirmar que el archivo antiguo se mantendrá actualizado automáticamente: para soportar CLIENTES todavía sin actualizar, el MASTER necesita conservar la publicación compatible del MQC2 legacy hasta que dejen de depender de él, o asumir explícitamente el riesgo de que su fallback envejezca.

### Primera actualización del addon: retirar las cuatro unidades antiguas

El `addon.xml` en `develop` sigue en `2.3.1`, y los flags de activación permanecen `False`. El motor actual puede detener/deshabilitar legacy e instalar v2 **en laboratorios**, pero no borra sus archivos unit en el camino de éxito y no restaura unidades antiguas desde journal después del borrado. Falta integrar un flujo seguro e idempotente:

1. **Nada de reconstruir biblioteca:** los `.strm` viven en almacenamiento interno y la transición afecta solo los montajes de contenido remoto.
2. No cortar montajes cuando Kodi está reproduciendo, aunque exista caché: esta no garantiza continuidad; esperar reproducción inactiva. Guardar antes un snapshot durable privado de las cuatro unidades antiguas y credenciales.
3. Deshabilitar cuatro legacy; detener y comprobar desmontaje real; instalar 2 FUSE + 4 bind; verificar mountinfo, seis unidades y lectura mínima de archivo conocido.
4. Marcar `ACTIVE` duradero y **solo después**, si existe recuperación de unidades desde snapshot, eliminar **exclusivamente** estos cuatro ficheros de `/storage/.config/system.d/`: `rclone_tvshows_1.service`, `rclone_tvshows_2.service`, `rclone_videos_1.service`, `rclone_videos_2.service`. La eliminación exige correspondencia exacta de bytes/propietario y unidades deshabilitadas/inactivas; `daemon-reload`; si falla una retirada, dejar `CLEANUP_PENDING` sin desmontar v2.
5. En siguientes inicios no recrear legacy ni repetir el corte. Tras una interrupción a mitad de camino, restaurar los servicios viejos desde el journal o recuperar v2 con un estado inequívoco, nunca ambos activos sobre la misma ruta. La pérdida de corriente puede dejar el **cambio de servicios** inconcluso; no implica borrar `.strm` ya persistidos.

La existencia de dispositivos todavía sin actualizar es inevitable porque las actualizaciones de Kodi no son atómicas entre equipos; el requisito no es coexistencia activa de legacy y v2 **en un mismo equipo**. Por diseño los archivos MQC2 separados permiten clientes antiguos en otros dispositivos, aunque la política de mantenimiento de ambos endpoints sigue pendiente.

**Estado verificable:** `REAL_SYSTEMD_LOCAL_2FUSE_4BIND=PASS`, `CONFIG_ROUTE_SPLIT_PURE_TESTS=PASS`, `V2_REMOTE_FILE_PUBLISHED=NO`, `V2_MASTER_WRITER_WIRED=NO`, `V2_CLIENT_RECOVERY_WIRED=NO`, `AUTO_CUTOVER_WIRED=NO`, `LEGACY_UNIT_CLEANUP_WIRED=NO`, `RELEASE_AUTHORIZED=NO`. Las tres banderas siguen en `False`.

**GitHub CI** para el selector de ruta: 657/657 Python OK, [run 44419097420](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44419097420). No valida el acceso al endpoint v2 todavía inexistente.

### 19/11/2026 — MASTER v2 crea MQC2 en GitHub si falta y actualiza cambios verificados

Se implementa (bajo flags **False**) el camino MASTER v2 `rclone_two_mount_master_sync.py` + `rclone_two_mount_master_runtime.py`, conectado al worker `rclone_token_sync.tick()`. Contra `cloud.masqelec/develop/rclone/rclone-v2.conf.crypt`: HEAD autenticado+GET; si 404 crea con PUT sin SHA, si 200 comprueba opciones/refresh y actualiza con SHA, si igual no escribe. Candidato cifrado MQC2 y fuentes local 0600; sondas OAuth en copia temporal por cada remoto cambiado, recaptura local, CAS sin retry 409/422 y readback autenticado posterior. Protege las cuentas Google y no toca el viejo `rclone/rclone.conf.crypt`. CI **704/704 PASS**, [Actions 44421911947](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44421911947).

**AÚN NO:** fichero v2 real (no existe en cloud), prueba real OneDrive/GitHub, limpieza legacy automática ni recuperación CLIENTE v2. `RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED=False` + `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False` + `RCLONE_TOKEN_SYNC_ENABLED=False`: ningún PUT en Kodi actual. [Runbook](MASTER_V2_GITHUB_SYNC_2026-11-19.md).
