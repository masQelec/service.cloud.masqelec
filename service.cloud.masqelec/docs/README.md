# Documentación técnica — `service.cloud.masqelec`

## Próximo desarrollo prioritario — mantenimiento IPTV/PVR de Kodi

- [**Especificación definitiva: PVR / Kodi, limpieza segura de huérfanos y Scan/Clean**](PVR_KODI_MAINTENANCE_DESIGN_2026-11-20.md) — alcance vigente, hechos confirmados, fallos del código, diseño de reconciliación, gates y prompt del siguiente chat.
- [Auditoría técnica e historial de decisiones IPTV/PVR/EPG](HANDOFF_IPTV_PVR_EPG_2026-11-20.md) — evidencia y evolución del diagnóstico; cuando haya discrepancia, prevalece la especificación definitiva.

**Incidencia confirmada por el operador:** Tvheadend actualiza correctamente su M3U cada 60 minutos; Kodi incorpora canales nuevos pero retiene antiguos. La limpieza de huérfanos de TVxx.db **no debe suprimirse sin reemplazo verificado**.

**Índice vigente: 20-11-2026.** Versión 2.3.2: MASTER y CLIENT
piloto con 2 FUSE + 4 bind, `rclone.conf` general sin OneDrive y
reproducción confirmada. Antes de limpiar se verificó 1025/1025 tests; después,
957/957 tests PASS en GitHub Actions. La recuperación OAuth después de una revocación real sigue
**sin validar**. El mantenimiento de pruebas y herramientas se describe
en [REPO_CLEANUP_2026-11-20.md](REPO_CLEANUP_2026-11-20.md).

**Documentos fechados del 17–19 de noviembre:** son un historial de
decisiones y resultados de laboratorio. Cuando digan `NO DEPLOY` o
`PENDING` se refieren a la fecha indicada, no al estado actual.

## Estado MASTER / recuperación — archivo de situación del 19-11-2026

La regresión confirmada por el operador antes del candidato de recuperación
temprana es **798/798 PASS**. MASTER: `MASTER_READINESS=PASS_READ_ONLY`,
11/11 controles correctos; `system.d` root:root modo 0755. El corte real
no se ha ejecutado.

- [Sistema de archivos KodiELEC/CoreELEC y rutas persistentes](KODIELEC_COREELEC_FILESYSTEM_AND_PATHS.md).
- [Auditoría userdata frente a journal persistente](USERDATA_VS_RECOVERY_STORAGE_AUDIT_2026-11-19.md).
- [Recuperación temprana previa a Kodi — candidato sin instalar](EARLY_BOOT_RECOVERY_KODIELEC_2026-11-19.md).
- [**Handoff 19-11-2026: cutover automático de addon**](HANDOFF_AUTO_CUTOVER_2026-11-19.md) — código, riesgos, gates y comandos de prueba.

**Nota histórica del 19-11 (ya superada en el piloto)**:
el coordinador de recuperación temprana exige un orden systemd de arranque
todavía no verificado en TX3/X96 X4. No hay servicio de recuperación
instalado ni activación del addon v2.

## Manual funcional del mantenimiento (vigente)

El [README principal](../../README.md) es ahora el punto de entrada operativo:
**qué se ejecuta al arrancar, qué se repite, qué cambia en MASTER/CLIENT,
PVR/EPG, catálogo, MyVideos, actualización de sistema y rclone**.

La [auditoría funcional de mantenimiento del 20-11-2026](AUDIT_MAINTENANCE_2026-11-20.md)
recoge trazabilidad de los módulos, riesgos de interrupción PVR,
diferencia entre intento y finalización de Scan/Clean y mejoras pendientes
en [Issue #4](https://github.com/masQelec/service.cloud.masqelec/issues/4).

## Documentación mantenida (fuente de trabajo)

| Documento | Cuándo consultarlo |
| --- | --- |
| [Limpieza de herramientas y tests (20-11)](REPO_CLEANUP_2026-11-20.md) | Criterios de retirada, dependencias, límites y gate CI |
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
| [Piloto aislado 2 FUSE + 4 bind](TWO_FUSE_FOUR_BIND_LOCAL_LAB_2026-11-18.md) | Preflight sin cambios, piloto local opcional, pruebas CI y pasos para KodiELEC |
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

## Fase siguiente: staging privado en el arranque (18-11-2026)

Código en `develop` (commit `3553df3b`, corrección de fixture de test `c782b1c2`): se ha integrado en la fase 1 de `service.py`, **después** de `start_cloud_storage()`, la llamada a `lib/rclone_two_mount_startup_stage.py`. Está protegida por un nuevo flag real:

```python
RCLONE_TWO_MOUNT_STAGING_ENABLED = False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED = False
RCLONE_TOKEN_SYNC_ENABLED = False
```

Con el flag de staging `False`, no se invocan las lecturas ni el generador y no se escribe ningún fichero; el código legacy sigue igual. En una versión futura **expresamente habilitada**, con credenciales locales válidas, generará un staging privado de **dos configs OneDrive+crypt, seis propuestas de unidades y un manifiesto sin secretos**, partiendo del `rclone.conf` local ya renovado por el propio rclone. No consulta OAuth, no usa tokens del MQC2 para sustituir los locales, no recorre directorios OneDrive, no instala unidades ni toca los cuatro montajes Kodi.

Ubicación RESERVADA para esa versión futura (no creada en ningún equipo por estos commits): `/storage/.config/masqelec/rclone-v2-staging/2026-11-17-two-fuse-v1/`. Permisos: directorio raíz y candidato `0700`; `account1.conf`, `account2.conf` y manifiesto `0600`; propuestas de unidades `0644` dentro del directorio privado. El manifiesto distingue `credential_source=existing_local_config_unverified`, `activation=stage_only` y `live_install_allowed=false`. **No afirmar que MQC2 haya sido autenticado por el staging**: no lo descarga.

Controles: valida inventario `crypt→OneDrive`, las cuatro unidades legacy compatibles, fuentes locales regulares (no enlaces simbólicos) y configuración `0600`; comprueba datos y metadatos de origen antes/después de generar; prepara un directorio temporal privado y lo mueve a su destino final sin tocar `system.d`. Reintento con la misma fuente = `already_staged` sin reescribir. Si rclone renovó después el refresh local y el contenido staged difiere, = `blocked_stale_or_unsafe_stage`: **el borrador antiguo no se instala ni se reescribe automáticamente**. La recuperación/reemplazo versionado del staging obsoleto y el cutover reversible se implementarán más adelante; no forzar etapas.

**Evidencia:** fallo inicial del test por no modificar el token ficticio correcto, corregido sin cambiar código de producción; CI final en [GitHub Actions run 44201463687](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44201463687) = **371/371 OK**, 19 pruebas nuevas. Es prueba sintética de filesystem aislado, **no** ejecución en KodiELEC ni autorización de migración.

Próximo paso: piloto de verificación read-only de prerrequisitos KodiELEC y, posteriormente, **dos FUSE + cuatro bind exclusivamente en rutas alternativas**, prueba de reproducción y rollback. El modo operativo legacy seguirá intacto hasta autorización explícita.



## Transición reversible: readiness de FUSE y fusión OAuth local (18-11-2026)

Implementado en `develop`: los cuatro servicios bind generados tienen **espera limitada de FUSE (30 × 1 s)** y se niegan a montarse encima de las cuatro rutas Kodi si ya son mountpoints. Compatibilidad `Type=simple` conservada; no se introduce `Type=notify`. Nuevo `lib/rclone_two_mount_token_rollback.py` **puro** para conservar dos tokens OneDrive aislados al volver a cuatro rclone, sin alterar Google Drive/crypt y bloqueando cambios concurrentes o identidad distinta. **424/424 tests OK** — [GitHub Actions 44356523812](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44356523812). No hay ejecutor de cutover, copias instaladas ni ensayo real de OneDrive; el staging sigue en ruta privada distinta de los `ACCOUNT_CONFS` de las unidades. **NO activar banderas**. [Protocolo y pendientes](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

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


### MASTER listo para preparación; ejecutor live aún bloqueado (18-11-2026)

El operador confirmó `PREFLIGHT_RESULT=PASS_READ_ONLY` con `CONFIG`, `LEGACY_UNITS`, `LEGACY_MOUNTS`, `LEGACY_SERVICES`, `NEW_MOUNTS_ABSENT`, `NEW_UNITS_ABSENT`, `ROLLOUT_STATE_LEGACY` = PASS. Sin OAuth, cambios de sistema ni verificación de playback. Implementados motor puro, gate Kodi JSON-RPC, journal persistente y escritura exclusiva de artefactos, **sin adaptador systemd real**. **507/507 tests PASS** (GitHub Actions [44361419430](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44361419430)); no activación ni rollback operativo. Ver [protocolo](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### Adapter local v2, 530/530 CI OK (18/11/2026)

Se añadió `lib/rclone_two_mount_live_adapter.py` al código de `develop` con ejecución explícitamente deshabilitada por defecto y sin integración en `service.py`. Revalida montajes legacy sin apilamientos, usa journal y operaciones systemd limitadas, conserva tokens locales, y exige leer un fichero conocido de cada cuenta antes de marcar ACTIVE (límite 15 s por lectura; no explora OneDrive). CI **530/530 PASS**: [run 44364099119](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44364099119). **NO probado con systemd/OneDrive reales; no cutover, no boot recovery.** Riesgo de escritura OAuth concurrente sobre `rclone.conf` aún sin cerrar. [Detalles y próximos gates](TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

| [Handoff 18-11: recuperación y OAuth sin clobber](HANDOFF_2026-11-18_CRASH_RECOVERY.md) | Estado actual de cutover, tests 588/588, rollback con drop-ins, condiciones pendientes |

| [Piloto real systemd aislado 2 FUSE + 4 bind](TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md) | Comandos KodiELEC, seguridad, limpieza y límites; 617 tests sintéticos |

| [Inventario OAuth MASTER/CLIENTES sin secretos](FLEET_OAUTH_INVENTORY_2026-11-18.md) | Script standalone de lectura, alcance de `/proc`, gates de flota y ejecución por dispositivo |

| [Arquitectura decidida: autoactualización y recuperación OAuth v2](AUTO_UPDATE_TWO_MOUNT_ARCHITECTURE_2026-11-18.md) | Kodi distribuye el addon; cada nodo migra automáticamente; MASTER publica MQC2 y CLIENTE usa token local hasta error real |

| [Distribución MQC2 legacy/v2 y primera limpieza systemd](AUTO_UPDATE_TWO_MOUNT_ARCHITECTURE_2026-11-18.md) | Nombres de archivo por versión, escritor/lector OAuth pendientes y eliminación segura de unidades antiguas |

| [Sincronización MASTER v2 con GitHub](MASTER_V2_GITHUB_SYNC_2026-11-19.md) | 404 crea, cambios comprobados actualizan, CAS/readback, banderas desactivadas, riesgos legacy pendientes |

| [Primer arranque automático y limpieza de legacy](AUTO_FIRST_RUN_CUTOVER_2026-11-19.md) | Orden transaccional, bloqueo por reproducción, limpieza idempotente, interruptores de release y gates reales |

### 19/11/2026 — detección automática de medios de prueba por cuenta en .strm locales

Nuevo `lib/rclone_two_mount_media_samples.py`: selecciona sin red una ruta de prueba por cada cuenta OneDrive leyendo únicamente los `.strm` del catálogo local (`/storage/videos` y `/storage/tvshows`). Validación de symlinks/traversal, <=8192 bytes por archivo, recorrido acotado a 200k entradas/12 s/8 niveles y **sin imprimir rutas**. Integrado en `rclone_two_mount_autostart.tick()` cuando `RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES=()`: no precisa configuración manual por cliente. Playback ocupado difiere sin explorar; fase unsafe permite recuperar sin muestras. CLI de solo lectura `--inventory` imprime `PASS_2_LOCAL_STRM_ACCOUNTS` o bloqueo, sin tocar montajes/OneDrive. **773/773 CI PASS** ([44426001148](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44426001148)).

**AÚN PENDIENTE:** preflight físico en MASTER y CLIENTE, confirmar existencia real de los vídeos tras levantar v2, ensayo cutover+rollback/reboot. Mantener flags desactivadas. [Procedimiento y script](AUTO_FIRST_RUN_CUTOVER_2026-11-19.md).
