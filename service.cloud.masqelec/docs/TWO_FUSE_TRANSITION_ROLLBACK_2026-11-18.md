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

## Diagnóstico REAL y seguro antes del corte (18-11-2026)

El operador pidió avanzar rápido hacia la transición, conservando la distinción funcional existente MASTER/CLIENTES y sin cortar reproducción a ciegas.

**Implementado:** `tools/rclone_two_mount_transition_preflight.py` es un solo archivo descargable por SSH y **exclusivamente lectura**. Su `--preflight` verifica la configuración canónica `rclone.conf` (dos cadenas crypt→OneDrive con refresh, dos Drive), que las cuatro unidades legacy siguen apuntando al canónico y usan `--read-only`, cuatro FUSE reales activos y sin apilamientos, cuatro servicios `systemctl is-active`, ausencia de nuevas raíces y unidades v2 instaladas y ausencia de marcador de transición. No escribe a `/storage`, no envía credenciales, no realiza OAuth y no modifica montajes/systemd. Nunca revela contenido del config. La salida sólo indica PASS/BLOCKED. Un resultado `PASS_READ_ONLY` **NO autoriza** el cutover ni comprueba reproducción inactiva.

**Descarga fijada a la revisión de código validada**:

```sh
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/a6d4d70f8a9a361a1b148654d7a52a07c18d38e3/service.cloud.masqelec/tools/rclone_two_mount_transition_preflight.py' -O /tmp/rclone_two_mount_transition_preflight.py && python3 -m py_compile /tmp/rclone_two_mount_transition_preflight.py && python3 /tmp/rclone_two_mount_transition_preflight.py --preflight
```

**Evidencia:** [GitHub Actions 44358176820](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44358176820) con `Ran 440 tests ... OK` (16 nuevas pruebas del preflight). La primera ejecución no pasó por un fixture sintético que no modificaba el refresh correcto; corregido y CI final PASS. No confundir con fallo del dispositivo.

Salida deseada:

```text
CONFIG=PASS
LEGACY_UNITS=PASS
LEGACY_MOUNTS=PASS
LEGACY_SERVICES=PASS
NEW_MOUNTS_ABSENT=PASS
NEW_UNITS_ABSENT=PASS
ROLLOUT_STATE_LEGACY=PASS
PREFLIGHT_RESULT=PASS_READ_ONLY
```

**PENDIENTES:** prueba real de inactividad Kodi, ubicación segura y durable de los dos snapshots 0600 y su instalación transaccional, secuencia ejecutora con rollback comprobado tras caídas, ensayo de credenciales/crypt/OneDrive real y reproducción. `CUTOVER_EXECUTOR=NOT_IMPLEMENTED`, `CUTOVER_AUTHORIZED=NO`, los tres flags quedan `False`. Mientras esto no exista, no ejecutar `systemctl stop` ni tocar `/storage/.mnt/`. Los montajes de producción siguen intactos.


## MASTER: preflight real PASS y motor transaccional aún sin adaptador (18-11-2026)

**Evidencia textual del operador en KodiELEC MASTER** (solo lectura, no activación):

```text
LAB_MODE=TWO_FUSE_TRANSITION_READ_ONLY
ONEDRIVE_ACCESSED=NO
LIVE_CONFIG_WRITE=NO
RCLONE_TOKEN_VALUES_PRINTED=NO
MOUNT_OR_SYSTEMD_MUTATIONS=NO
PLAYBACK_IDLE=NOT_VERIFIED
CUTOVER_AUTHORIZED=NO
CONFIG=PASS
LEGACY_UNITS=PASS
LEGACY_MOUNTS=PASS
LEGACY_SERVICES=PASS
NEW_MOUNTS_ABSENT=PASS
NEW_UNITS_ABSENT=PASS
ROLLOUT_STATE_LEGACY=PASS
PREFLIGHT_RESULT=PASS_READ_ONLY
```

**Interpretación estricta:** el MASTER tiene la configuración local y las cuatro unidades/montajes legacy correctos, sin restos visibles de v2; junto con el piloto local ficticio `PASS_LOCAL_FUSE_BIND_LAB` confirma prerrequisitos. **No prueba reproducción inactiva, crypt/OneDrive v2 ni posibilidad de rollback de montajes reales.** Ningún servicio real se ha detenido, instalado, habilitado ni reiniciado.

### Código preparado en `addon/develop`

- `lib/rclone_two_mount_cutover_engine.py`: motor de transición con **adaptador inyectado**, sin I/O ni servicios. Bloqueado por defecto salvo gates booleanos estrictos de autorización, Kodi inactivo y rollback preparado. Pasos de parada legacy, instalación, arranque 2 FUSE/4 bind, verificación, marcador ACTIVE; ante fallo, secuencia de rollback. Si no se pueden desmontar los bind/FUSE nuevos, o recuperar tokens, devuelve `MANUAL_RECOVERY_REQUIRED` sin arrancar legacy encima de los nuevos. La excepción/terminación del proceso requiere journal y recuperación operativa real, todavía NO integrados.
- `lib/rclone_two_mount_kodi_idle.py`: función pura que consulta `Player.GetActivePlayers` mediante callback JSON-RPC de Kodi. Solo `result=[]` explícito = inactivo; errores, música/vídeo activo y respuestas ambiguas bloquean. **No se ha conectado todavía a Kodi real**.
- `lib/rclone_two_mount_journal.py`: archivos privados 0600 en directorio 0700, lock exclusivo y fases `prepared → cutover_started → active` o `rollback_required → legacy_restored`. Guarda respaldo canónico y cuatro unidades legacy y sincroniza a disco. Detecta interrupciones como recuperación manual requerida. **No está conectado todavía con el marcador de arranque ni con los servicios**; por tanto NO garantiza recuperación automática tras reboot.
- `lib/rclone_two_mount_atomic_install.py`: instalación de ficheros candidatos 0600/0644 con enlace duro sin sobrescribir, sincronización a disco y retirada conservadora por contenido esperado. No llama `systemctl`, no modifica la configuración activa por sí solo. **No usar para reemplazar a ciegas rclone.conf**: la sustitución de un canónico con otros escritores de OAuth requiere una estrategia adicional de concurrencia.

**Pruebas:** CI final **507/507 PASS**, [run 44361419430](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44361419430). Hay 21 tests del motor con fallos inyectados, 9 del gate Kodi, 22 del journal y 15 del instalador; todas sintéticas. La compatibilidad real de bloqueo `flock`, instalación y nueva reproducción en KodiELEC sigue pendiente.

### GATE que impide activar hoy

```text
REAL_KODI_IDLE_VERIFIED=NO
REAL_SYSTEMD_ADAPTER_CONNECTED=NO
CRASH_RECOVERY_ON_BOOT_VERIFIED=NO
REAL_ONEDRIVE_CRYPT_TWO_FUSE_TEST=NO
CUTOVER_EXECUTOR_LIVE=NO
RCLONE_TWO_MOUNT_STAGING_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TOKEN_SYNC_ENABLED=False
LIVE_KODI_MOUNTS_CHANGED=NO
```

**Siguiente trabajo SIN desviar el objetivo:** un único adaptador local a `systemctl` + journal + montaje y conciliación de dos tokens al volver a legacy, con pruebas de caída/reinicio; acto seguido, ventana de reproducción inactiva y piloto real en MASTER con permiso específico. No construir coordinador de flota, no cambiar catálogo STRM/función MASTER-CLIENTES, no activar nada automáticamente mientras siga faltando una de esas garantías.

## Adaptador local systemd — prototipo SIN ACTUALIZADOR (18-11-2026)

**Nuevo módulo:** `lib/rclone_two_mount_live_adapter.py`, con `LocalAdapter(live_enabled=False)` por defecto. **NO hay llamada desde `service.py`, ni `--apply` operativo**. Código únicamente en `addon/develop`, no copiado al equipo KodiELEC.

La propuesta une `rclone_two_mount_cutover_engine` con el journal privado, las instalaciones exclusivas y el gate de reproducción Kodi. Revalida las cuatro unidades y montajes legacy **sin apilamientos**, origen crypt y tokens locales, y exige marcador ausente y nombres libres. Antes de detener legacy escribe respaldo duradero, un marcador `cutover_started` que `rollout.mode()` considera `unsafe`, y bloquea el actualizador legacy. Detiene las cuatro unidades, lee el canónico más reciente tras la parada, genera dos configuraciones individuales y seis servicios, arranca dos FUSE y cuatro bind; `Type=simple` se acompaña de esperas de disponibilidad. No crea listados `rclone lsf` ni modifica las bibliotecas.

**Nuevo gate obligatorio para marcar ACTIVE:** `known_media_files=(ruta_1,ruta_2)` con **una ruta multimedia exacta por cuenta OneDrive**, extraída de un `.strm` ya conocido. Deben comenzar por `/storage/.mnt/videos/1/` o `/storage/.mnt/tvshows/1/` y `/storage/.mnt/videos/2/` o `/storage/.mnt/tvshows/2/` respectivamente. No se recorre el sistema remoto: se lee solo 1 byte por archivo con un subproceso Python y límite de 15 segundos por archivo, sin imprimir contenidos. Si no están disponibles, el estado ACTIVE se deniega. **El gate no acredita aún reproducción multimedia completa desde Kodi.**

**Rollback previsto, NO validado en equipo:** detener los cuatro bind y los dos FUSE; comprobar que ambos procesos escritores realmente estén inactivos; recuperar los tokens actualizados de los dos `account*.conf` y conciliarlos con el canónico local sin reemplazar Google Drive/crypt; restaurar cuatro servicios legacy y verificar montaje. Persistencia de journal bajo bloqueo exclusivo. Si se detecta un conflicto de identidad, estado o tokens, se suspende la recuperación automática y requiere intervención.

**Evidencia:** [GitHub Actions 44364099119](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44364099119): **530/530 tests OK** (incluye 18 tests nuevos del adaptador y 3 del sondeo multimedia con timeout, además de los 507 anteriores). Todas las pruebas del adaptador usan montajes/systemd simulados y rutas temporales. El MASTER real solo ha pasado preflight y piloto FUSE/bind **local ficticio**.

### Gates de lanzamiento aún cerrados

1. **Reinicio abrupto:** journal permite detectar estado interrumpido pero **no existe recuperador de boot validado**. No decir «rollback automático garantizado» ni usar el código durante apagones o reinicios probables.
2. **Escritores del canónico OAuth:** la lectura-validación previa a `os.replace` no es un CAS coordinado con otros rclone que puedan modificar tokens de Google Drive. Se debe excluir escritor concurrente o implantar una recuperación que no reescriba el canónico compartido.
3. **Reproducción inactiva y recuperación real:** el callback JSON-RPC de Kodi no está integrado en la versión desplegada; no se ha ejecutado `systemctl stop/start` real para v2, ni prueba `.strm` real.
4. **Operación final:** confirmar rutas conocidas (una por cuenta), backup cerrado, orden y rollback de todos los servicios, y ensayar en ventana sin reproducción. La función `execute_with_local_lock` exige argumentos de autorización, y el constructor está deshabilitado por defecto: **no utilizarla todavía como un comando de operación**.

```text
MASTER_PREFLIGHT_READ_ONLY=PASS_REAL
KODIELEC_TWO_FUSE_FOUR_BIND_LOCAL=PASS_REAL
GITHUB_CI=530/530_PASS
ADAPTER_CODE=IMPLEMENTED_DISABLED_PROTOTYPE
ADAPTER_ATTACHED_TO_ADDON=NO
REAL_ONEDRIVE_CUTOVER=NOT_EXECUTED
REAL_BOOT_CRASH_RECOVERY=NOT_VERIFIED
RCLONE_TWO_MOUNT_STAGING_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TOKEN_SYNC_ENABLED=False
```

## 18-11-2026 — cierre de riesgos críticos: arranque y OAuth compartido

**Verificado en addon/develop:** [GitHub Actions 44378128654](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44378128654), **552/552 tests PASS** (Python 3.11). La prueba real MASTER legacy `PREFLIGHT_RESULT=PASS_READ_ONLY` y el laboratorio ficticio 2 FUSE+4 bind `PASS_LOCAL_FUSE_BIND_LAB` siguen siendo la única evidencia física: **no** se ha ejecutado el cutover con OneDrive.

### 1) Arranque tras interrupción: fail-closed real en código del addon

Nuevo módulo `lib/rclone_two_mount_boot_guard.py` integrado en **`lib/cloud_storage.py`** y **`service.py::_mounts_ready()`**. Lee exclusivamente el journal persistente y el marcador de arquitectura. Si falta el journal pero hay un marcador v2, si el journal está corrupto, si la fase quedó `cutover_started`/`rollback_required`, o si `active` no tiene flag autorizado y marcador compatible: **bloquea el actualizador de servicios legacy y el escaneo Kodi**. Si no hay journal ni marcador, no cambia el funcionamiento legacy. Un journal `prepared` o `legacy_restored` sin marcador permite legacy; una fase `active` con bandera habilitada y marcador correcto permite continuar a la validación independiente de mountinfo. Se evita el reinicio ciego de cuatro servicios encima de montajes v2.

**Importante**: no detiene systemd automáticamente, no decide el montaje sano por sí solo, y **NO restaura los servicios tras un reinicio brusco**. Si hubo corte, devuelve bloqueo conservador para revisión de las rutas y credenciales. Las unidades habilitadas en systemd pueden arrancar antes del addon; queda por ensayar físicamente un reinicio interrumpido.

### 2) OAuth: no reemplazar jamás el canónico compartido sin excluir otros escritores

La función de rollback del adaptador ya **no utiliza `os.replace` sobre `/storage/.config/rclone/rclone.conf`**. Si al parar rclone v2 los dos tokens OneDrive han cambiado, construye una copia conciliada (OneDrive actualizado, Google Drive/crypt existentes intactos) dentro del journal privado en `canonical-recovery-candidate.conf`, con permisos 0600, y devuelve `MANUAL_RECOVERY_REQUIRED`. Si no hubo cambio, no escribe el canónico y puede continuar la reversión. La copia privada permite recuperar tokens recientes sin enviarlos a GitHub ni sustituir los de Google Drive. Se incluyen pruebas integradas que verifican archivo canónico intacto aun con rotación.

**Esta decisión prioriza no perder credenciales**: un rollback completamente automático con refresh OneDrive renovado NO está resuelto; necesita un procedimiento exclusivo para parar cualquier escritor del canónico (incluidos posibles procesos Google Drive) y una prueba real de reanudación. Una comprobación inode/mtime antes del reemplazo no es suficiente; rclone no respeta el `flock` del addon. No reintroducir esa carrera.

### 3) Cambio seguro de unidades en reinicio

El adaptador impide `execute_with_local_lock` si `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`, incluso si un llamador pasa `authorized=True`. En `mark_active`, después de verificar 2 FUSE+4 bind y lecturas conocidas, primero deshabilita las **cuatro unidades legacy** y **después** habilita las nuevas; no deja en ningún punto las dos familias habilitadas a la vez. Un apagón en medio podría dejar montajes sin autoarranque, pero nunca hace que el propio adaptador mantenga ambas familias habilitadas. El journal/marker siguen siendo la fuente de advertencia. No hay autorización de producción.

### Evidencias y siguientes gates

- Tests sintéticos y de integración (sin systemd real): **552/552 PASS**, CI `44378128654`.
- Bandera `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; `RCLONE_TWO_MOUNT_STAGING_ENABLED=False`; `RCLONE_TOKEN_SYNC_ENABLED=False`. Ningún comando operativo publicado ni instalación en KodiELEC.
- **Pendiente antes de activar**: ensayo controlado del adaptador con systemd real/archivo conocido de cada cuenta, un recuperador tras reinicio real (o procedimiento manual probado), manejo del conflicto OAuth de forma que no bloquee rollback con renovación real, reproducción .strm y verificación del comportamiento tras el próximo arranque.
- MASTER/CLIENTES y ZIP/STRM intactos. Los clientes siguen importando catálogo sin escanear OneDrive.


## Actualización 2026-11-18 — recuperación desde journal y rollback OAuth sin clobber

La última implementación de `addon/develop` incluye **reversión de dos a cuatro montajes con tokens OneDrive renovados mediante cuatro drop-ins systemd privados**, sin escribir en `rclone.conf`; recuperación **explícita** desde journal tras perder RAM por reboot; bloqueo al arranque si falta un drop-in/credencial de recuperación; y health kernel-only sin listados periódicos remotos. La arquitectura MASTER/CLIENTE no cambió. CI **588/588 PASS** en [run 44383466775](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44383466775). Los únicos PASS físicos siguen siendo el piloto 2 FUSE+4 bind LOCAL y el preflight legacy de solo lectura. **Sin activación, sin prueba de systemd drop-in real, sin corte OAuth/OneDrive real, sin recuperación automática en boot.** Documento actualizado: [HANDOFF_2026-11-18_CRASH_RECOVERY.md](HANDOFF_2026-11-18_CRASH_RECOVERY.md).
