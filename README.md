# Cloud masQelec — servicio Kodi/KodiELEC

**Addon:** `service.cloud.masqelec` · **versión declarada:** `2.3.1` (`addon.xml`) · **lenguaje:** Python 3 / Kodi · **estado del desarrollo:** laboratorios en `develop`; arquitectura de montajes y OAuth v2 **no desplegada**.

> **Estado auditado: 17-11-2026.** Última ejecución comunicada por el operador: **228 pruebas, OK**. Los laboratorios de concurrencia, aislamiento, 2 FUSE + 4 bind y reconciliación OAuth en memoria devolvieron **PASS**. Falta ejecutar el **preflight MQC2 + SHA remoto de GitHub** y las pruebas de montaje FUSE/bind reales. Los resultados previos **no autorizan** cambiar las unidades de los equipos.

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

En `develop` se incorporaron cinco pruebas nuevas y dos barreras: `--real-probe` falla con `BLOCKED_FLEET_COORDINATION` aunque no existan montajes rclone locales; `--preflight` lee el MQC2 desde el commit GitHub fijado y comprueba también `GH_BRANCH_COMMIT_STABLE=YES` para detectar cambios del HEAD remoto. Commits: `17cb2901`, `41b9f033`, `c701e74e`, `75cb8b48`. **La suite ampliada aún no tiene una ejecución confirmada**; el último `228/228 OK` corresponde al corte previo. El preflight en KodiELEC sigue **PENDIENTE**.
