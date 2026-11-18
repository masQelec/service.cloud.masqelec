# Transición 4 FUSE → 2 FUSE + 4 bind — preparación reversible

**18-11-2026 · addon/develop · NO DEPLOY · NOT READY FOR CUTOVER.**

## Estado verificado

El operador ejecutó en KodiELEC real el laboratorio **local ficticio** con salida:

```text
LAB_MODE=RCLONE_TWO_FUSE_FOUR_BIND_LOCAL
ONEDRIVE_ACCESSED=NO
RCLONE_LIVE_CONFIG_READ=NO
KODI_PATHS_CHANGED=NO
SYSTEMD_WRITE=NO
GITHUB_UPLOAD=NO
LAB_RESULT=PASS_LOCAL_FUSE_BIND_LAB
```

Este PASS verifica el esquema de 2 FUSE + 4 bind sobre archivos de prueba, su lectura y desmontaje. **No acredita** que dos montajes `users_library_N:` con OAuth/crypt puedan sustituir con seguridad a los cuatro montajes legacy, que tokens reales estén vigentes, ni recuperación/reproducción Kodi. No modificar la lógica MASTER/CLIENTE ni el catálogo STRM: MASTER escanea contenidos de OneDrive y publica los cambios; CLIENTES aplican el ZIP y escanean solo los STRM locales; ambos reproducen desde las cuatro rutas montadas que deben seguir intactas.

## Código nuevo implementado, sin instalar

1. `lib/rclone_two_mount_plan.py`: raíz de cada cuenta sigue siendo `Type=simple`, compatible con las unidades legacy. Cada bind `Type=oneshot` declara `BindsTo=` y `After=` respecto de su FUSE, **rechaza de inmediato un destino Kodi que ya sea punto de montaje** y espera hasta 30 comprobaciones de un segundo a que la raíz FUSE sea un punto montado y la subcarpeta específica exista. Timeout de activación bind: 45 segundos. Esto resuelve la carrera de `Type=simple` que da servicio por arrancado cuando el proceso existe pero FUSE aún no está montado. Una comprobación `test -d` puede consultar metadatos de una subcarpeta: NO hace un escaneo recursivo de la biblioteca de CLIENTES.
2. `lib/rclone_two_mount_token_rollback.py`: función **pura**, `reconcile_canonical_for_rollback(baseline_raw, current_raw, account1_raw, account2_raw)`. Tras detener los dos rclone v2 (condición del FUTURO operador), reconstruye en memoria la configuración canónica de seis secciones con los tokens OneDrive actuales de los dos snapshots aislados. Se preservan las secciones Google Drive y las opciones `crypt` del canónico presente; se prohíben cambios de identidad, cambio concurrente del token OneDrive canónico o intercambios entre cuentas. No escribe ficheros, no ejecuta rclone/servicios, no conecta con Microsoft; NO valida que el token siga siendo válido externamente.
3. El módulo `lib/rclone_two_mount_startup_stage.py` **sigue desactivado**, y NO es un instalador: prepara los dos `account*.conf` y las unidades dentro de `/storage/.config/masqelec/rclone-v2-staging/<candidate>/`. Las unidades generadas esperan para su ejecución archivos **distintos**, en `/storage/.config/rclone/isolated-mounts/account{1,2}.conf`. Antes de cualquier cutover aún se necesita un instalador local atómico que copie los dos snapshots al destino esperado con modo 0600, respete el token más reciente al parar legacy y verifique rutas. **Esta fase NO ha sido implementada.**

CI: **424/424 pruebas PASS** en [GitHub Actions 44356523812](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44356523812), incluyendo 16 casos nuevos de conciliación (tokens rotados, Google intacto, rechazo de cuentas cambiadas, JSON inválido y cambios concurrentes) y 2 casos nuevos del arranque bind. Son pruebas sintéticas Python, no una transición real.

## Secuencia necesaria para el FUTURO ejecutor, aún inexistente

**ANTES** (no ejecutar en KodiELEC como comandos de esta fase): identificar si el dispositivo es MASTER o CLIENTE solo para saber el riesgo operativo y pausar tareas de biblioteca/reproducción; ambos usan las mismas rutas rclone. Probar que no hay reproducción en curso. Preparar y verificar copias recuperables de cuatro unidades legacy y `rclone.conf` sin filtrarlas; no instalar unidades ni sobrescribir tokens durante la preparación. Comprobar cuatro montajes legacy sanos y leer su config en el instante seguro.

**CORTE LOCAL (PENDIENTE DE IMPLEMENTAR/PROBAR):** parar cuatro montajes legacy solo durante una ventana de inactividad, generar los dos snapshots desde el último canónico leído, escribirlos atómicamente en el destino de trabajo privado, habilitar dos raíces FUSE con una cuenta cada una, esperar raíz FUSE real, habilitar los cuatro bind hacia las **mismas cuatro rutas Kodi**. Confirmar vínculo root/bind mediante `/proc/self/mountinfo`, comprobar lectura de un archivo conocido con ruta exacta (nunca `rclone lsf` ni barrido global de los CLIENTES) y reproducción Kodi antes de declarar `active`. No reiniciar legacy sobre un mount v2.

**REVERSIÓN (PENDIENTE DE IMPLEMENTAR/PROBAR):** detener binds en orden inverso y los dos escritores FUSE, leer sus `account*.conf` tras la parada para rescatar tokens que rclone haya renovado; fusionar solo los dos tokens OneDrive con el canónico cuya identidad y estado previo sigan siendo compatibles. Guardar el canónico restaurado atómicamente sin pisar cambios concurrentes. Restaurar unidades legacy, reactivar sus cuatro montajes solo cuando las cuatro rutas estén libres y verificar `mountinfo` y reproducción. Si falta una cuenta, el canónico ha cambiado inesperadamente o los tokens no son verificables: **detener automatismo y requerir intervención; no restaurar a ciegas**.

**Riesgos todavía abiertos:** validez real de OAuth entre equipos, conservación de refresh en snapshots durante el traspaso, limpieza de montajes apilados en estados parciales, reintento de arranque tras reinicio brusco, coordinación con reproducción activa y activación automática tras actualización del addon. Ninguno está autorizado por el PASS sintético. No hace falta coordinador central de flota para este cambio local, pero sí preservar la autenticación de cada dispositivo.

## Flags permanentes de seguridad

```text
RCLONE_TWO_MOUNT_STAGING_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TOKEN_SYNC_ENABLED=False
CUTOVER_EXECUTOR=NOT_IMPLEMENTED
REAL_ONEDRIVE_V2_MOUNT=NOT_RUN
LIVE_UNITS_INSTALLED=NO
LIVE_KODI_MOUNTS_CHANGED=NO
GITHUB_OAUTH_PUT=NO
```

## Próxima tarea inmediata

**Programar el instalador y transicionador reversible local** con dry-run y comprobaciones reales de tokens/mountinfo, separado de `service.py` y de `cloud/develop/system.d`, pero **NO ejecutarlo** hasta que el operador confirme un ensayo en MASTER sin reproducción. En especial, resolver el traspaso desde el staging privado a los dos `ACCOUNT_CONFS` reales. Entonces revisar el mecanismo de arranque tras reinicio brusco y el estado de MASTER/CLIENTE sin tocar catálogo.
