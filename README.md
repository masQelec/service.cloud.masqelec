# Cloud masQelec — servicio Kodi/KodiELEC

**Addon:** `service.cloud.masqelec` · **versión declarada:** `2.3.1` (`addon.xml`) · **lenguaje:** Python 3 / Kodi · **estado del desarrollo:** laboratorios en `develop`; arquitectura de montajes y OAuth v2 **no desplegada**.

> **Estado actualizado: 18-11-2026.** GitHub Actions **588/588 OK** (Python 3.11). KodiELEC: ambas OneDrive `DIFFERENT` respecto al MQC2 tras renovación rclone confirmada por el operador; ambas Google Drive `SAME`. P0-B generaciones, P0-C flota y P0-D readback: **PASS solo en laboratorios**. La coordinación real MASTER/CLIENTES y el montaje 2 FUSE + 4 bind siguen **sin desplegar**.

## ¿Qué es?

Addon de servicio para la distribución masQelec basada en Kodi/KodiELEC. Coordina al arrancar la configuración cifrada de rclone, los servicios de montajes, las actualizaciones del sistema, la biblioteca de Kodi, el catálogo, los procesos PVR/Tvheadend y tareas de mantenimiento. Dispone de roles **MASTER** y **CLIENT**, detectados localmente (código en `lib/device_utils.py`), y utiliza un repositorio de configuración separado: **[masQelec/cloud.masqelec](https://github.com/masQelec/cloud.masqelec)**.

La versión de trabajo puede *preparar*, **sin activar**, una futura reducción de **cuatro procesos `rclone mount` a dos** manteniendo las mismas cuatro rutas de Kodi y preservando el cifrado `crypt` (contenido cifrado, nombres de archivos sin cifrar).

## Estado en una tabla

| Área | Estado real | Observación |
| --- | --- | --- |
| Servicio Kodi, biblioteca, PVR y actualización del sistema | Código existente | No equivale a una certificación de despliegue de OAuth v2. |
| Montajes actuales | **LEGACY: 4 procesos rclone / 4 FUSE** | Las unidades vigentes están en `cloud.masqelec/develop/system.d/`. |
| Configuración compartida | `/storage/.config/rclone/rclone.conf` | 2 remotos OneDrive + 2 Google Drive + 2 wrappers `crypt`. |
| Detección de procesos que escriben el mismo conf | **Lab real PASS** | Bloquea recuperación del fichero si hay montajes activos. |
| Aislamiento `crypt → OneDrive` | **Lab real PASS** | 4 configs propuestas, 2 cuentas coherentes. |
| Diseño 2 FUSE + 4 bind | **Plan y lab sin despliegue PASS** | Rutas de Kodi sin cambios; servicios nuevos no instalados. |
| Reconciliación OAuth v2 | **Política y lab sin escritura PASS** | No hay coordinador productivo conectado. |
| Verificador OAuth y publicación GitHub por SHA | **Código de laboratorio, pruebas unitarias OK** | No se han validado aún sobre la instalación real en su conjunto. |
| Compatibilidad con CLIENTES antiguos | **Preservada por diseño** | El backup MQC2 canónico seguirá siendo el formato objetivo. |
| Actualización/autodespliegue de la nueva arquitectura | **Prohibidos** | Manifiesto `stage_only`, activación individual pendiente. |

### Barreras de seguridad vigentes

```python
# service.cloud.masqelec/lib/constants.py (develop)
RCLONE_TOKEN_SYNC_ENABLED = False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED = False
```

**No habilitar esas banderas por haber superado 228 pruebas.** La opción `--real-probe` está ahora **bloqueada incluso sin montajes locales**, porque no se puede demostrar que otros CLIENTES estén inactivos. No habilitarla sin coordinación de flota y pruebas específicas.

## Estructura

```text
README.md                         # esta página
service.cloud.masqelec/
├── addon.xml                     # addon Kodi, versión 2.3.1
├── service.py                    # secuencia de arranque y workers periódicos
├── resources/settings.xml        # ajustes de usuario
├── lib/
│   ├── cloud_storage.py          # MQC2 inicial y unidades systemd LEGACY
│   ├── device_utils.py           # rol MASTER / CLIENT
│   ├── updater.py                # actualización del SISTEMA por rclone
│   ├── update_library.py         # BD MyVideos, cachés y flujo de biblioteca
│   ├── update_pvr.py             # PVR/Tvheadend/playlist
│   ├── core_catalog.py           # catálogo .strm, publicación y sincronización
│   ├── rclone_token_*.py         # política y worker OAuth legacy (desactivado)
│   ├── rclone_mount_isolation.py  # dependencias crypt -> OneDrive
│   ├── rclone_two_mount_*.py     # propuesta 2 FUSE, estado, OAuth, salud, CAS
│   └── ...                       # red, cifrado, logging y fiabilidad
├── tools/                        # laboratorios controlados; ver OPERATIONS
├── tests/                        # suite unittest sin Kodi real
└── docs/                         # documentación y handoff
```

**Atención:** `auto_update` de `resources/settings.xml` invoca `updater.update_system()`, que gestiona **paquetes del sistema** desde rclone y `/storage/.update`; **no implementa un despliegue automático del código del addon ni del nuevo esquema FUSE a todos los CLIENTES**.

## Modos de trabajo y ramas

| Ámbito | Uso |
| --- | --- |
| `service.cloud.masqelec/develop` | Desarrollo, pruebas, documentación y laboratorios. **Rama activa de este proyecto.** |
| `service.cloud.masqelec/main` | Rama estable del addon: no modificar sin autorización de release. |
| `cloud.masqelec/develop` | Datos y unidades de desarrollo; contiene el manifiesto **no operativo** del piloto en `rollouts/`. |
| `cloud.masqelec/master` | Configuración estable: no modificar en estos trabajos. |
| Rol MASTER / CLIENT | Afecta a catálogo y reconciliación. **No confundir rol** con `main`/`master` de Git. |
| LEGACY / `prepared` / `active` / `unsafe` | Estados por dispositivo, definidos en `rclone_two_mount_rollout.py`. Solo LEGACY está autorizado ahora. |

**Regla:** primero código en `develop` + pruebas de Ubuntu; después laboratorios de **solo lectura** en KodiELEC; ninguna prueba crea por sí sola permiso de despliegue. No actualizar `cloud/develop/system.d/` con las unidades v2: el arranque legacy puede ejecutar `systemctl try-restart` de las unidades que cambien.

## Flujo de arranque (existente)

1. Kodi inicia `service.py` y detecta rol, versión, red y ZeroTier.
2. `start_cloud_storage()` obtiene la reserva MQC2, comprueba identidad de remotos, protege tokens locales compatibles y gestiona las unidades legacy. **Este flujo puede cambiar archivos o reiniciar servicios antiguos en circunstancias determinadas: no es un laboratorio.**
3. Ejecuciones secuenciales: correcciones de ajustes, actualización de **sistema** si corresponde, BD/biblioteca, PVR y mantenimiento de arranque.
4. Workers periódicos: PVR, actualización/limpieza de biblioteca y tick OAuth. El tick OAuth está **sin efecto** mientras la bandera esté desactivada.

La salud de los montajes legacy exige 4 `fuse.rclone`. El modo v2 añade la comprobación por `/proc/self/mountinfo` de **2 FUSE raíz + 4 bind**, pero no se activa.

## Desarrollar y validar

En Ubuntu, tras sincronizar `develop`:

```bash
cd ~/GitHub/service.cloud.masqelec
git switch develop
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

**Referencia confirmada por el operador:** `Ran 228 tests ... OK` (17-11-2026). Este número es un control histórico, no una garantía de que futuras versiones conserven exactamente 228.

**Prueba siguiente recomendada en KodiELEC (sin OAuth real):**

```bash
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/c701e74e5a677e3d300094f9ea112eb830749c3f/service.cloud.masqelec/tools/rclone_two_mount_real_probe_lab.py' \
  -O /tmp/rclone_two_mount_real_probe_lab.py
python3 -m py_compile /tmp/rclone_two_mount_real_probe_lab.py
python3 /tmp/rclone_two_mount_real_probe_lab.py --preflight
```

Este `--preflight` descarga y valida el respaldo MQC2 publicado: **lectura, no escritura**; no ejecuta consultas OAuth. Si falla por divergencia local/GitHub, conservar ambos estados y analizar; no sobrescribir tokens. **No ejecutar `--real-probe` con montajes activos**.

## Documentación

La documentación mantenida está en [**docs/README.md**](service.cloud.masqelec/docs/README.md):

- [Arquitectura y modos](service.cloud.masqelec/docs/ARCHITECTURE_AND_MODES.md)
- [Operaciones y pruebas](service.cloud.masqelec/docs/OPERATIONS_AND_TESTING.md)
- [Seguridad y auditoría](service.cloud.masqelec/docs/SECURITY_AUDIT.md)
- [CLIENTES: distribución, compatibilidad y migración](service.cloud.masqelec/docs/CLIENT_ROLLOUT.md)
- [Progreso, decisiones y trabajo pendiente](service.cloud.masqelec/docs/ROADMAP_AND_PROGRESS.md)
- [**Handoff para otro chat — 17-11-2026**](service.cloud.masqelec/docs/HANDOFF_2026-11-17.md)
- [Documentos históricos de los laboratorios](service.cloud.masqelec/docs/README.md#historial-de-laboratorios)

## Reglas de contribución y seguridad

- Un solo objetivo: **consolidar `develop`**; no abrir ramas innecesarias, no fusionar a `main` sin aprobación.
- Nunca pegar `rclone.conf`, `token`, `refresh_token`, contraseñas `crypt`, `authorized_keys` o claves MQC2 en GitHub Issues, README, logs o chats.
- Las copias de pruebas con credenciales deben estar en `/tmp` privado (directorio `0700`, archivos `0600`) y eliminarse al terminar.
- No interpretar `LAB_RESULT=PASS` como autorización de release. Registrar commit, comando, entorno, salida, alcance y **lo que NO se probó**.
- El refresco de token en una **copia** puede tener efectos en Microsoft; evitar comprobaciones reales con escritor(es) activo(s).
- El protocolo de publicación OAuth no puede usar reintentos 409/422 con un SHA nuevo; requiere comprobación estricta de concurrencia y confirmación posterior.
- Cualquier operación de transición de montajes requiere plan de rollback por dispositivo y ventana sin reproducción.

**Estado de release a 17-11-2026: `NO DEPLOY`; `NO LIVE UNIT CHANGE`; `NO GITHUB CREDENTIAL UPLOAD`.**

### Endurecimiento posterior al corte documental (17-11-2026)

En `develop` se incorporaron cinco pruebas nuevas y dos barreras: `--real-probe` falla con `BLOCKED_FLEET_COORDINATION` aunque no existan montajes rclone locales; `--preflight` lee el MQC2 desde el commit GitHub fijado y comprueba también `GH_BRANCH_COMMIT_STABLE=YES` para detectar cambios del HEAD remoto. Commits: `17cb2901`, `41b9f033`, `c701e74e`, `75cb8b48`. **La suite ampliada quedó validada en GitHub Actions: 233/233 OK** sobre el commit `70543894` (run `44188131468`). Los 228/228 corresponden al corte anterior comunicado por el operador. El preflight en KodiELEC sigue **PENDIENTE**.


**CI registrado (17-11-2026):** workflow `develop unit tests (no deployment)` con `permissions: contents: read`, checkout sin credenciales persistentes y Python 3.11. Run: https://github.com/masQelec/service.cloud.masqelec/actions/runs/44188131468; `Ran 233 tests in 0.359s / OK`. Esto **no** verifica ejecución en KodiELEC, dispositivos remotos, publicación GitHub MQC2 ni migración real. `main`, `cloud/master`, `cloud/develop/system.d` y montajes no se han modificado.

### Discrepancia real OAuth detectada (17-11-2026)

El preflight KodiELEC confirmó SHA GitHub, autenticación MQC2 e identidad estática, pero devolvió **BLOCKED_BASELINE_DIVERGED**. Una o más de las cuatro cuentas OAuth presentan refresh diferentes; no es prueba de caducidad. La rama `develop` incorpora un informe por proveedor/cuenta sin secretos, sin modificar las fuentes. Pruebas GitHub Actions **239/239 OK** (commit `07b008d`); falta repetir el preflight de diagnóstico en KodiELEC. Ver [informe de incidencia](service.cloud.masqelec/docs/PREFLIGHT_BASELINE_DIVERGENCE_2026-11-17.md).

### P0-B/P0-D: ventanas de generación y readback (17-11-2026)

La suite ampliada quedó en **271/271 OK**, GitHub Actions [run 44194785936](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44194785936). Se incorporaron un control puro de generaciones/ABA, que sin contadores compartidos con rclone bloquea, y un verificador puro de readback MQC2/GitHub por SHA/commit. Ninguno está conectado a producción, y **P0-C (coordinación interdispositivo) permanece pendiente**. Véase [informe P0-B/P0-D](service.cloud.masqelec/docs/OAUTH_GENERATIONS_CAS_LAB_2026-11-17.md).

### Coordinación OAuth P0-C (laboratorio)

Modelados inventario global, exclusión de legacy/offline/desconocidos, confirmaciones por dispositivo, epochs y coherencia conjunta de las dos OneDrive con la fuente MQC2 (sin publicación). **CI 322/322 OK**. Sin coordinador real o integración con rclone, ninguna prueba demuestra exclusión operativa. Microsoft no invalida automáticamente los refresh antiguos al renovarlos: la divergencia no prueba revocación. [Documento técnico P0-C](service.cloud.masqelec/docs/OAUTH_FLEET_COORDINATION_P0C_2026-11-17.md).

### Actualización del addon y migración local (corrección de arquitectura)

Los CLIENTES reciben actualizaciones del addon y arrancan con el código nuevo. MASTER publica catálogo; CLIENTES reproducen mediante rutas `.strm` idénticas. La versión definitiva preparará en cada dispositivo 2 FUSE + 4 bind a partir de sus credenciales locales, sin coordinador central ni lecturas de directorios para poblar la biblioteca. Nuevo modelo de decisión de arranque y 15 tests; GitHub Actions **352/352 PASS**. **Sin activación**. [Procedimiento](service.cloud.masqelec/docs/ADDON_STARTUP_ROLLOUT_2026-11-17.md).

### Preparación privada al iniciar el addon (18-11-2026)

La fase 1 del addon tiene un hook **desactivado** para preparar localmente dos `account*.conf`, dos propuestas FUSE, cuatro bind y un manifiesto sin secretos. No instala unidades ni requiere inspeccionar los directorios de OneDrive. El token de origen es el `rclone.conf` local, no una restauración forzada del MQC2. **371/371 PASS** en GitHub Actions; staging real de KodiELEC **NOT RUN**. [Diseño y resultados](service.cloud.masqelec/docs/ADDON_STARTUP_ROLLOUT_2026-11-17.md).

### Laboratorio aislado 2 FUSE + 4 bind (18-11-2026)

Disponible el preflight independiente y un piloto opcional con dos fuentes **locales ficticias**: no toca OneDrive, `.strm` ni montajes Kodi. Pruebas sintéticas **401/401 PASS** en CI; la ejecución física en KodiELEC sigue **NOT RUN**. [Instrucciones detalladas](service.cloud.masqelec/docs/TWO_FUSE_FOUR_BIND_LOCAL_LAB_2026-11-18.md).

### Preflight KodiELEC — bloqueo explicado (18-11-2026)

El preflight real halló `RCLONE_MOUNT_FLAGS=NO` con FUSE y herramientas de montaje disponibles. Se corrigió el falso negativo posible por buscar `--config` (global) en `rclone mount --help` y un bug de detección FUSE del script standalone. **406/406 tests PASS en CI**, segundo preflight real pendiente. [Protocolo corregido](service.cloud.masqelec/docs/TWO_FUSE_FOUR_BIND_LOCAL_LAB_2026-11-18.md).

### Arranque seguro y rollback OAuth (18-11-2026)

Generadas unidades bind que esperan de forma acotada al montaje FUSE de `Type=simple` y una función pura para reintroducir en el canónico los tokens OneDrive renovados por dos montajes aislados, sin tocar Google Drive. **424/424 tests CI PASS**. No hay migración automática ni instalación. [Pendientes y controles](service.cloud.masqelec/docs/TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### Preflight real de transición 4→2 (18-11-2026)

Disponible verificación standalone de configuración, cuatro servicios legacy/mountinfo y ausencia de unidades v2; **solo lectura**. Suite 440/440 OK. El diagnóstico del MASTER debe preceder a cualquier corte. [Comando y gates](service.cloud.masqelec/docs/TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### Transición transaccional v2 — 18/11/2026

El MASTER ha pasado el preflight **real de solo lectura**. Preparados motor de transición/rollback con inyección de fallos, gate Kodi inactivo, journal privado y escritura exclusiva. **507/507 tests CI OK**. Aún falta el adaptador systemd y probar cutover/reinicio reales; flags apagados. [Procedimiento](service.cloud.masqelec/docs/TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### Adaptador local desactivado, sin cambios de producción (18/11/2026)

Prototipo para ejecutar transición y rollback con journal, Kodi idle, dos FUSE y cuatro bind; pruebas **530/530 OK**. El MASTER sigue con los cuatro montajes legacy. Pendiente recuperación tras reboot y coordinación de escritura OAuth. [Protocolo](service.cloud.masqelec/docs/TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### 18/11/2026 — guardas de arranque y protección OAuth

La migración v2 continúa sin desplegar. El addon bloquea actualizaciones legacy y escaneos si detecta una transacción v2 interrumpida; la reversión conserva tokens nuevos en journal privado **sin sobrescribir el canónico compartido**. 552/552 pruebas OK. La recuperación automática con tokens rotados y un reinicio real siguen pendientes. [Detalles](service.cloud.masqelec/docs/TWO_FUSE_TRANSITION_ROLLBACK_2026-11-18.md).

### 18/11/2026 — motor de recuperación y tokens aislados

Versión `develop` con **588/588 tests PASS**. El rollback puede volver a los cuatro montajes con refresh OneDrive renovado usando configuración privada y drop-ins systemd, sin sobrescribir el canónico de Google Drive. Disponible recuperación explícita desde journal tras interrupción. Sin deploy, sin prueba de crypt real y con flags apagados. [Handoff actualizado](service.cloud.masqelec/docs/HANDOFF_2026-11-18_CRASH_RECOVERY.md).

### KodiELEC: laboratorio systemd real, aislado (18-11-2026)

Preparado script para comprobar **2 FUSE + 4 bind gestionados por systemd** sin OneDrive y sin cambiar los 4 montajes legacy. Preflight solo lectura y ejecución temporal bajo `/tmp` con unidades runtime aleatorias. **617/617 pruebas sintéticas OK**; ensayo real pendiente del usuario. [Runbook](service.cloud.masqelec/docs/TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md).

### Primer ensayo real de systemd: diagnóstico pendiente (18-11-2026)

KodiELEC: preflight READY; piloto `FAIL_SERVICE_START` con `CLEANUP=COMPLETE`. Preparado diagnóstico de unidad fallida, 622/622 tests CI OK; aún **no** existe PASS systemd real. [Runbook y siguiente comando](service.cloud.masqelec/docs/TWO_FUSE_SYSTEMD_ISOLATED_LAB_2026-11-18.md).
