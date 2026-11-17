# OAuth v2 — reconciliación 2 FUSE y CLIENTES legacy (NO ACTIVADO)

Fecha 2026-11-17; addon \`develop\`. El operador confirmó 179/179
tests PASS y laboratorio \`TWO_FUSE_FOUR_BIND_CLIENT_READY\` PASS.

## Compatibilidad obligatoria

El MASTER con 2 mounts usará exactamente 2 configuraciones privadas:
- account1.conf = [users_library_1] crypt + su remoto OneDrive real
- account2.conf = [users_library_2] crypt + su remoto OneDrive real

Se preservan todas las opciones de \`crypt\`, incluido
\`filename_encryption = off\`: los contenidos siguen cifrados, los
nombres de archivos no. La política valida que las secciones de cada
configuración sean exactamente las dependencias del wrapper, sin copiar
las credenciales de la otra cuenta ni las Google Drive.

El formato publicado a GitHub debe continuar siendo EL MISMO archivo
canónico \`rclone/rclone.conf.crypt\`, cifrado MQC2 con las seis secciones
(dos crypt + dos OneDrive + dos Drive), porque los CLIENTES legacy
dependen de él y aún son compatibles. No cambiar esa ruta ni cifrado.

## Política implementada ahora (solo funciones puras)

\`lib/rclone_two_mount_oauth.py\`:

- \`prepare_master(canonical, (account1, account2), published)\`: valida
  inventario, dependencias, contraseñas crypt y ajustes estáticos de
  todos los remotos. **Si canonical y published difieren en cualquier
  refresh_token, bloquea la selección**: ni expiry ni mtime sirven como
  reloj de rotaciones. Si los dos snapshots no cambian devuelve
  \`unchanged\`. Si alguno cambia, devuelve el candidato canónico de
  seis secciones con SOLO los tokens OneDrive cambiados y estado
  \`candidate_requires_probe\`. No se toca Google Drive.
- \`probe_gate(prepared, results)\`: sólo acepta \`ok\` para TODOS los
  OneDrive modificados y entonces devuelve
  \`revalidate_sources_before_publish\`, **no** \`published\`.
  Un fallo de cuota, red, 401 o resultado desconocido bloquea la
  publicación. Antes de publicar habrá que revisar nuevamente el
  contenido y generaciones de los dos ficheros, el canónico y el
  estado remoto, así como los tokens eventualmente ROTADOS POR EL
  PROPIO SONDEO en su copia temporal.
- \`prepare_client(canonical_master, index, isolated, auth_failure)\`:
  prepara el token OneDrive alternativo de UNA cuenta SOLO si hubo
  fallo OAuth inequívoco; conserva crypt y la cadena de remotos. Devuelve
  \`candidate_requires_probe_and_safe_apply\`, jamás lo instala
  mientras el proceso rclone mount puede actualizar su propio archivo.

Es una política de reconciliación, NO el publicador ni el coordinador
en caliente. No tiene llamadas de red, escrituras, systemctl, mount,
umount ni logs de secretos.

## Implementación operativa pendiente: BLOQUEANTE

1. Convertir el candidato en un reconciliador de snapshots estables,
   con generación dev/inode/ctime/mtime, sin perder rotaciones.
2. Verificar credenciales mediante pruebas rclone con copias 0600,
   capturando si el propio sondeo ha refrescado los tokens.
3. Impedir decisiones stale si cambió una fuente/replica o el backup
   MQC2 durante verificación/publicación. Sin CAS interproceso de
   rclone, una sustitución con mounts activos NO es segura.
4. Construir y ensayar la publicación MQC2 canónica desde MASTER v2.
5. Probar coexistencia real de CLIENTES legacy y v2, recuperación
   selectiva de una cuenta sin reiniciar Kodi en reproducción.
6. Validar rclone Type=notify y los 4 bind con rutas temporales,
   después plan de cutover y rollback por dispositivo.
7. Poner gates/versiones a la actualización del paquete v2 de
   CLIENTES, sin systemctl try-restart en el arranque.

## Gates vigentes

RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
TWO_MOUNT_OAUTH_V2_PUBLISH_ENABLED=NO (sin bandera operativa)
TWO_MOUNT_CLIENT_AUTO_ACTIVATE=NO
TWO_MOUNT_DEPLOY_EXECUTED=NO
NO_LIVE_SERVICE_UNIT_CHANGE=YES
NO_GITHUB_CREDENTIAL_UPLOAD=YES

El manifiesto público en \`cloud.masqelec/develop/rollouts\` sigue
\`auto_apply=false\` y \`production_authorized=false\`.

La batería anterior fue 179 PASS. Se añadieron 23 pruebas de política,
total previsto 202, aún pendiente de ejecución por el operador.

## Ensayo adicional con seis secciones reales, sin claves ni OAuth externo

`tools/rclone_two_mount_oauth_lab.py` descarga el código de una
referencia inmutable y lee **únicamente** el `rclone.conf` actual.
Las dos configuraciones crypt/OneDrive se construyen en memoria. El
respaldo MQC2 remoto no se consulta en este ensayo, por lo que se utiliza
la configuración canónica local como referencia para comprobar la política;
esto NO prueba ausencia de divergencias frente a GitHub.

Se prueba el caso normal sin rotación (no publicar), un refresh_token
FICTICIO sustituido solo en memoria (exigir validación rclone y
bloquear su promoción) y la ruta de recuperación selectiva de un CLIENTE
(sondeo + aplicación segura todavía pendientes). La simulación **no**
realiza solicitudes de autenticación ni guarda el marcador inválido.
Comprueba además que crypt, Google Drive y la configuración real no
cambiaron. El ensayo no instala unidades ni reinicia montajes.

    wget -q https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/develop/service.cloud.masqelec/tools/rclone_two_mount_oauth_lab.py -O /tmp/rclone_two_mount_oauth_lab.py
    python3 -m py_compile /tmp/rclone_two_mount_oauth_lab.py
    python3 /tmp/rclone_two_mount_oauth_lab.py

Salida buscada: CANONICAL_LAYOUT=PASS,
ISOLATED_CRYPT_ONEDRIVE_CONFIGS=2,
BASELINE_POLICY=UNCHANGED,
SIMULATED_ROTATION=REQUIRES_REAL_PROBE,
GOOGLE_DRIVE_AND_CRYPT_PRESERVED=PASS,
CLIENT_SELECTIVE_RECOVERY=PROBE_AND_SAFE_APPLY_REQUIRED,
LIVE_CONFIG_CHANGED=NO, LAB_RESULT=PASS.

Estos resultados NO habilitan un publicador ni una recuperación en caliente.
