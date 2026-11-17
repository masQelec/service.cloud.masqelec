# Handoff — two FUSE / four bind, MASTER + CLIENTES, 2026-11-17

## Evidencia y compatibilidad

- El operador confirmó: 152/152 tests PASS en la fase anterior.
- Laboratorio aislado MASTER 4 remotos OAuth + 2 secciones auxiliares: PASS.
- Laboratorio de aislamiento: las 4 unidades apuntan a wrappers crypt;
  cada cadena equivale a crypt -> OneDrive, 2 secciones, 1 token OAuth.
- Los datos están cifrados, los nombres NO: no cambiar los ajustes
  crypt ni desactivar el cifrado de datos.
- El diseño de esta fase mantiene exactamente las rutas de Kodi:
  /storage/.mnt/videos/1, /storage/.mnt/videos/2,
  /storage/.mnt/tvshows/1, /storage/.mnt/tvshows/2.

## Arquitectura candidata (NO desplegada)

Dos procesos rclone:
- rclone_library_1.service monta users_library_1: (crypt raíz) en
  /storage/.mnt/cloud/1. Fuente: config aislada account1.conf.
- rclone_library_2.service monta users_library_2: (crypt raíz) en
  /storage/.mnt/cloud/2. Fuente: config aislada account2.conf.

Cuatro servicios *oneshot* de bind:
- masqelec_bind_videos_1 -> cloud/1/movies -> videos/1
- masqelec_bind_tvshows_1 -> cloud/1/tvshows -> tvshows/1
- masqelec_bind_videos_2 -> cloud/2/movies -> videos/2
- masqelec_bind_tvshows_2 -> cloud/2/tvshows -> tvshows/2

Los bind dependen de la unidad rclone correspondiente mediante
BindsTo/After. Cada unidad bind verifica que su destino no esté ya
montado antes de montar: no se puede activar mientras los antiguos
FUSE sigan ocupando esas rutas. Type=notify debe verificarse contra el
binario rclone real de KodiELEC antes de autorizar una migración.

Se generan solo en un laboratorio /tmp con permisos privados. La
configuración canonica original, systemd y la reproducción no se tocan.

## Distribución de versiones a CLIENTES

No actualizar los cuatro archivos operativos en
cloud.masqelec/develop/system.d/ durante el piloto: cloud_storage.py
los descarga al inicio y hace systemctl try-restart si detecta cambios.
Ese comportamiento podría cortar reproducción a toda la flota.

La referencia de versión se publica fuera de esa ruta:
cloud.masqelec/develop/rollouts/rclone-two-mount/v1/manifest.json.
Es un MANIFIESTO NO OPERATIVO, sin contraseñas ni OAuth.
Siempre declara auto_apply=false y production_authorized=false.
La app puede incorporar soporte de esta versión, descargar y validar
el manifiesto, y preparar planes locales sin cambiar los montajes.

La actualización del addon ya existente ocurre en service.py
mediante update_system() cuando auto_update está habilitado y Kodi está
inactivo; esta función no autoriza migrar unidades.

Cada CLIENTE conserva marcador local (no en GitHub):
/storage/.config/masqelec/rclone-mount-mode.json
schema=1, layout=two-fuse-v1, state=prepared|active.
El fichero no se crea ni se modifica automáticamente en esta fase.

- Sin marcador: legacy; se mantienen los cuatro servicios y los
  cuatro FUSE actuales.
- prepared: solo distribución/ensayo, aún gestionado por cloud_storage
  legacy; no se paran servicios.
- active: no aplicar el actualizador legacy; debe existir ya un
  sistema de actualización v2 específico antes de autorizarlo.
- marcador inválido, symlink o active con flag deshabilitado: unsafe;
  se bloquea el actualizador legacy y se requiere intervención manual.

RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False en constants.py.
RCLONE_TOKEN_SYNC_ENABLED=False. No hay migrador/activador automático.

service._mounts_ready() utiliza el modo legacy por defecto. Para modo
active comprueba /proc/self/mountinfo: debe haber dos FUSE raíz y cuatro
bind de las subcarpetas exactas, con mismo dispositivo, source y tipo.
Además exige que las cuatro rutas de Kodi sean legibles y no vacías.
Un error de marcador falla cerrado (no devuelve disponibilidad).

## Renovaciones OAuth: bloqueador del despliegue

Con dos procesos hay un escritor local por cuenta, pero existen muchos
CLIENTES que pueden renovar refresh_token de la misma cuenta OneDrive.
El MASTER publica el backup MQC2 del rclone.conf canónico histórico.
La nueva configuración utiliza account1.conf y account2.conf separados:
el código OAuth actual NO los reconcilia, por tanto NO se puede activar
este diseño en MASTER ni CLIENTES todavía.

Futuras tareas obligatorias:
1. Coordinar renovaciones de account1.conf y account2.conf sin alterar
   crypt ni Google Drive; una rotación en un CLIENTE no debe imponerse
   al MASTER sin validación real por rclone.
2. Probar que la restauración en caliente no pisa una renovación
   concurrente de un proceso activo; no usar os.replace sin CAS.
3. Validar el soporte real de Type=notify en KodiELEC.
4. Ensayar FUSE raíz y bind en rutas **nuevas de laboratorio** primero.
5. Probar coexistencia de clientes legacy y v2. No deshabilitar
   los cuatro servicios antiguos hasta verificar las cuatro rutas.
6. Procedimiento de rollback: desactivar bind nuevos, detener solo
   los 2 rclone nuevos, restaurar configs/units legacy preservadas,
   reactivar los 4 servicios y verificar Kodi. Solo con reproducción
   detenida y autorización del operador.
7. Habilitar actualización versionada y segura del paquete v2 sin
   reiniciar unidades activas durante la descarga de cambios.
8. Validar backup/restore de estado y evitar una doble activación tras
   reboots o actualizaciones del addon.

## Comandos de comprobación, SIN DESPLIEGUE

Ubuntu:
    python3 -m unittest discover -s service.cloud.masqelec/tests -p "test_*.py"

KodiELEC:
    wget -q https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/develop/service.cloud.masqelec/tools/rclone_two_mount_plan_lab.py -O /tmp/rclone_two_mount_plan_lab.py
    python3 -m py_compile /tmp/rclone_two_mount_plan_lab.py
    python3 /tmp/rclone_two_mount_plan_lab.py

Ningún comando del laboratorio modifica /storage, la configuración
de rclone, systemd o los montajes. El directorio temporal y las
copias privadas se eliminan al finalizar.

## Estado de release

TWO_MOUNT_RELEASE_AUTHORIZED=NO
TWO_MOUNT_DEPLOY_EXECUTED=NO
TWO_MOUNT_LIVE_UNITS_MODIFIED=NO
TWO_MOUNT_FUSE_RESTART_EXECUTED=NO
TWO_MOUNT_CLIENT_AUTO_ACTIVATE=NO
MFA_RELEASE_AUTHORIZED=N/A
RCLONE_TOKEN_SYNC_ENABLED=False
