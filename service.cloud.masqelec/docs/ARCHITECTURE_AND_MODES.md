# Arquitectura, roles y modos — Cloud masQelec

**Fuente de verdad:** código de `develop` a 17-11-2026. Si un documento histórico difiere de este, comprobar el código/HEAD y actualizar el índice. No confundir *implementado* con *activado*.

## 1. Dos repositorios, dos responsabilidades

- **Addon**: `masQelec/service.cloud.masqelec`, con `README.md` en la raíz y el addon bajo `service.cloud.masqelec/`.
- **Datos y servicios**: `masQelec/cloud.masqelec`: `system.d/` (cuatro rclone + ZeroTier), `rclone/rclone.conf.crypt` (respaldo MQC2), `catalog/`, `userdata/`, `pvr/` y el manifiesto no operativo `rollouts/rclone-two-mount/v1/manifest.json`.
- En la rama actual, `constants.CLOUD_BRANCH="develop"`. Las ramas estables **no son el entorno de pruebas**.

El dato remoto cifrado no equivale a un token en claro seguro de publicar. Evitar copiar el blob, claves o credenciales a documentación. La clave local para MQC2 se deriva del primer registro válido de `/storage/.ssh/authorized_keys`; cambiar ese origen sin estrategia de rotación puede inutilizar el descifrado.

## 2. Roles del equipo: MASTER y CLIENT

`lib/device_utils.py` decide el rol:

- **MASTER** solo cuando coinciden una identidad de interfaz Ethernet autorizada y el nombre del nodo ZeroTier configurado.
- **CLIENT** en los demás casos o ante errores de detección.
- El resultado de `get_device_role()` se cachea por proceso. **No usar nombres de ramas Git como sinónimo de rol.**
- `MASTER` es la referencia para catálogo y futura publicación de reserva MQC2; `CLIENT` descarga catálogo y consume respaldos.
- Una cuenta OneDrive puede estar montada simultáneamente en muchos equipos. Reducir procesos en **cada equipo** no elimina las renovaciones de otros CLIENTES.

## 3. Flujo del addon de servicio

```text
Kodi inicia service.py (addon.xml, service start=startup)
  ├─ detectar rol, versión, red y ZeroTier
  ├─ FASE 1: cloud_storage.start_cloud_storage() [bloqueante]
  │    ├─ obtener MQC2, descifrar, comparar identidad
  │    ├─ preservar tokens locales compatibles
  │    └─ gestionar unidades systemd LEGACY y asegurar servicios
  ├─ ONE-SHOTS secuenciales
  │    ├─ fix_settings
  │    ├─ updater.update_system() [actualización del SO, no del addon]
  │    ├─ update_library
  │    ├─ update_pvr
  │    └─ startup_maintenance
  └─ WORKERS periódicos (cada 60 s evalúan preferencias y condiciones)
       ├─ PVR
       ├─ mantenimiento de biblioteca
       └─ rclone_token_sync.tick() [bloqueado por flag False]
```

Las tareas de mantenimiento consultan red, reproducción inactiva, salud de montajes y cooldown/circuit-breaker según la operación. **La salud de FUSE no garantiza OAuth vigente**: una caché puede responder con un token ya revocado.

`updater.py` compara `VERSION_ID` y `COREELEC_DEVICE`, baja un artefacto de actualización del sistema por rclone y lo prepara en `/storage/.update`. Los cambios de código del addon y los cambios de unidades v2 **no** se distribuyen mediante el manifiesto de forma automática actualmente.

## 4. Almacenamiento LEGACY — operativo

```text
                 /storage/.config/rclone/rclone.conf
                    │   │   │   │
                    ├── 2 remotos onedrive (OAuth)
                    ├── 2 remotos drive (OAuth: actualización/logs)
                    └── 2 wrappers crypt (opciones y contraseñas intactas)
                                   │
                             4 rclone mount
          ┌────────────────────────┼─────────────────────────┐
          ▼                        ▼                         ▼
 /storage/.mnt/videos/1  /storage/.mnt/videos/2     ...
 /storage/.mnt/tvshows/1 /storage/.mnt/tvshows/2
```

La relación operativa real en `cloud.masqelec/develop/system.d`:

| Unidad | Origen crypt | Destino Kodi |
| --- | --- | --- |
| `rclone_videos_1.service` | `users_library_1:movies` | `/storage/.mnt/videos/1` |
| `rclone_videos_2.service` | `users_library_2:movies` | `/storage/.mnt/videos/2` |
| `rclone_tvshows_1.service` | `users_library_1:tvshows` | `/storage/.mnt/tvshows/1` |
| `rclone_tvshows_2.service` | `users_library_2:tvshows` | `/storage/.mnt/tvshows/2` |

Cada wrapper `crypt` cifra **contenido**, pero conserva los nombres de archivo (`filename_encryption=off`). No cambiar `remote`, `password`, `password2` ni opciones de ruta: eso puede hacer ilegibles bibliotecas existentes.

**Problema legacy:** cada par películas/series de una cuenta comparte el mismo fichero; rclone puede renovar OAuth concurrentemente. El worker `rclone_token_sync` detecta escritores activos y bloquea la sustitución en caliente del fichero, pero **está desactivado**.

## 5. Arquitectura v2 propuesta — no activa

```text
MASTER o CLIENTE (por dispositivo)
  account1.conf [crypt + OneDrive 1] ---> rclone_library_1.service
                                      ---> /storage/.mnt/cloud/1 (FUSE)
                                             ├─ movies  --bind--> /storage/.mnt/videos/1
                                             └─ tvshows --bind--> /storage/.mnt/tvshows/1
  account2.conf [crypt + OneDrive 2] ---> rclone_library_2.service
                                      ---> /storage/.mnt/cloud/2 (FUSE)
                                             ├─ movies  --bind--> /storage/.mnt/videos/2
                                             └─ tvshows --bind--> /storage/.mnt/tvshows/2
```

- **Dos procesos rclone / dos archivos OAuth aislados / cuatro bind del kernel / cuatro rutas Kodi inalteradas.**
- Las unidades se generan mediante `lib/rclone_two_mount_plan.py`, con dependencia y prevención de montajes en destinos ya ocupados.
- `lib/rclone_two_mount_health.py` contrasta `/proc/self/mountinfo`: device, superblock FUSE, origen y subruta. La existencia de una carpeta **no** prueba que sea el bind correcto.
- El generador propone `Type=notify`, que aún debe verificarse con el binario rclone real de KodiELEC antes de autorizar la transición.
- **Cambia el aislamiento de fallos**: una caída del rclone de una cuenta interrumpe a la vez películas y series de esa cuenta. El rendimiento en producción todavía no se ha medido.

## 6. Modos de dispositivo y compatibilidad

El marcador previsto (`lib/rclone_two_mount_rollout.py`) es:

```text
/storage/.config/masqelec/rclone-mount-mode.json
```

Esquema exacto de candidato (documental; **no crear el archivo a mano**):

```json
{
  "schema": 1,
  "layout": "two-fuse-v1",
  "state": "prepared",
  "candidate_id": "2026-11-17-two-fuse-v1"
}
```

| Estado | Comportamiento previsto |
| --- | --- |
| Sin marcador | `legacy`: cuatro FUSE y mecanismo actual. |
| `prepared` | Sigue en legacy; solo ensayo y preparación. |
| `active` + flag autorizado | Reservado para futura migración por operador; bloquea actualizador legacy. |
| Inválido/symlink/versión distinta/active con flag deshabilitado | `unsafe`: bloquear actualizador legacy, exigir intervención. |

**Actualmente:** `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False` y no existe activador operativo. El manifiesto remoto es **stage_only** (`auto_apply=false`, `production_authorized=false`). No poner `state=active` como atajo.

## 7. OAuth, MQC2 y coexistencia

```text
  [MASTER v2: account1.conf + account2.conf]
                    │
           política de reconciliación
                    │
  [CANÓNICO: 2 crypt + 2 OneDrive + 2 Google Drive]
                    │
        MQC2 autenticado, mismo formato
                    │
      cloud/develop/rclone/rclone.conf.crypt
                 ┌──┴──┐
                 ▼     ▼
          CLIENT legacy  CLIENT v2 futuro
```

Los CLIENTES legacy requieren la estructura canónica de seis secciones. La política pura `rclone_two_mount_oauth.py` conserva `crypt`, los dos Google Drive y las identidades, y puede preparar en memoria solo los cambios OneDrive. No atribuye antigüedad a un refresh token por `expiry` ni mtime.

`rclone_two_mount_verify.py` ejecuta sondeos en COPIAS `0600` y captura posibles rotaciones de esos temporales. **Una copia privada no evita efectos de rotación en Microsoft**: el laboratorio `--real-probe` se bloquea ante montajes rclone activos y requiere coordinación externa de CLIENTES.

`rclone_two_mount_publish_guard.py` implementa un transporte GitHub con **SHA esperado, sin reintentos 409/422**, y exige confirmación posterior incluso con 200. No está conectado a un publicador activo. Quedan pendientes revalidaciones interproceso + política de promoción de tokens + prueba de coexistencia.

## 8. Arquitectura de seguridad y observabilidad

- `rclone.conf` real y tokens **fuera de GitHub en claro**; backup MQC2 autenticado en `cloud/develop`.
- Copias de laboratorio dentro de directorios temporales `0700`, archivos `0600`; destruir al finalizar.
- `rclone_token_policy.py` valida inventario/identidades y distingue AUTH real de cuota, red o permisos.
- `rclone_token_sync.py` contiene fences de montajes activos y generación del fichero; **no son locks compartidos con rclone**.
- El publicador legacy `catalog_utils._upload_file` reintenta SHA en conflictos; **no usarlo para OAuth v2**.
- `service.py` tiene workers y logs; `reliability_utils.py` persiste cooldown/métricas en `addon_data`. Evitar que los logs contengan credenciales.

Consultar [SECURITY_AUDIT.md](SECURITY_AUDIT.md) para amenazas, hallazgos y evidencia, y [CLIENT_ROLLOUT.md](CLIENT_ROLLOUT.md) antes de cambios que afecten equipos.
