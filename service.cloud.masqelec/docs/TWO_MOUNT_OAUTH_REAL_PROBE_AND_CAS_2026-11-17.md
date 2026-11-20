# MASTER OAuth v2 — sondeo real aislado y publicación CAS (2026-11-17)

Estado: **no desplegado, sin activación ni escritura de credenciales**.
Las 202 pruebas anteriores y el laboratorio \`TWO_MOUNT_OAUTH_RECONCILIATION_READ_ONLY\`
fueron PASS según salida del operador. No se han migrado montajes.

## Riesgo confirmado en la vía antigua

\`lib/catalog_utils.py::_upload_file\` reintenta HTTP 409/422 con un SHA
recién consultado. No reutilizar ese publicador para OAuth v2: podría
promover un candidato antiguo frente a uno más reciente. El SHA de
GitHub es una protección contra conflicto, no un reloj de refresh tokens.

## Componentes en laboratorio

- \`lib/rclone_two_mount_verify.py\`: lsf REAL de cada OneDrive usando una
  **copia privada** temporal \`0600\`, dentro de directorio \`0700\`.
  Nunca usa el \`--config\` del montaje activo. No escribe en OneDrive,
  pero puede renovar OAuth EN LA COPIA. Captura el contenido posterior
  y comprueba que se mantiene la identidad y el wrapper crypt original.
  Sus estados son ok/auth/rate_limited/unavailable/tampered. Nunca
  registra stderr del proveedor ni tokens.
- \`lib/rclone_two_mount_publish_guard.py\`: valida la respuesta contents
  GitHub (base64, Git SHA1 real del blob, MQC2 autenticado y cuatro
  tokens con la identidad esperada). Genera cifrado MQC2 **en memoria**.
  \`strict_put\` requiere tres autorizaciones explícitas y un callback
  HTTP. Realiza como máximo UN PUT con el SHA esperado; un 409/422
  detiene la publicación, sin subir con un SHA nuevo. Incluso HTTP 200
  devuelve \`accepted_requires_remote_confirmation\`; falta releer
  GitHub y verificar contenido de destino.
- Estos componentes NO están conectados a \`service.py\`, al worker
  programado ni al actualizador de CLIENTES.

## Riesgos pendientes que BLOQUEAN activar el publicador

1. Implementar y probar la captura simultánea con generación (dev,
   ino, ctime, mtime) de account1.conf, account2.conf y rclone.conf
   canónico. Revalidar su igualdad justo antes y después del PUT.
2. Si el sondeo produce un nuevo refresh_token en su copia temporal,
   decidir cómo reconciliarlo sin pisar la renovación del mount real;
   no publicar automáticamente el token sondeado.
3. Conservar dos Google Drive y los dos wrappers crypt exactos.
   No seleccionar refresh por fecha de expiry ni por mtime.
4. Relacionar el SHA del blob GitHub con el MQC2 descargado y
   comprobar de nuevo después del PUT. Otro equipo puede actualizar
   GitHub concurrentemente.
5. El MASTER y los CLIENTES tienen escritores diferentes para las
   mismas cuentas: un conflicto no permite elegir un token nuevo sin
   validar los dos candidatos.
6. Nunca reiniciar montajes ni alterar rutas de Kodi mientras reproduzca.
7. No instalar servicios ni activar flags hasta pruebas FUSE+bind reales
   en rutas alternativas y migración/rollback aprobados.

## Flags

\`RCLONE_TOKEN_SYNC_ENABLED=False\`
\`RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False\`
\`TWO_MOUNT_OAUTH_V2_PUBLISH_ENABLED=NO\` (sin activador operativo)
\`TWO_MOUNT_DEPLOY_EXECUTED=NO\`

Los CLIENTES antiguos continúan con la ruta MQC2
\`rclone/rclone.conf.crypt\` y los cuatro montajes. El manifiesto
\`cloud/develop/rollouts/rclone-two-mount/v1\` sigue en \`stage_only\`.

## Comprobaciones

Ubuntu: suite \`unittest discover\`. Previo: 202/202 PASS.
Nuevas pruebas: sondeo simulado, rotación en copia privada, fallo
401/429, cambio de crypt, decode SHA y MQC2, y PUT 409 sin retry.
Total previsto: **224**. Pendiente de confirmar en Ubuntu.

KodiELEC: el laboratorio de sondeo real, sin upload ni escritura live,
requiere lectura de MQC2 GitHub y la opción explícita \`--real-probe\`.
No ejecutarlo durante un corte de conectividad. Un PASS no autoriza
a realizar publicación en vivo ni migración de CLIENTES.

## Laboratorio KodiELEC: SSH/device key, GitHub SHA y OAuth REAL

`tools/rclone_two_mount_real_probe_lab.py` descargará módulos desde
el commit inmutable `636866996cd72551ef37eb4439c6f023d5c3561d`.
Obtiene la clave del dispositivo desde authorized_keys con el mismo
algoritmo SHA256 utilizado en el laboratorio MASTER anterior. El GET
HTTP público de GitHub Contents descarga la copia MQC2 sin necesidad
de exponer el token personal de GitHub, valida el Git blob SHA contra
los bytes cifrados y autentica el contenido MQC2 con la clave local.

Después comprueba que la identidad estática de las seis secciones sea
idéntica y que los refresh_token del respaldo y del canónico no diverjan.
Una diferencia bloquea el avance: no se elige automáticamente el más nuevo.

Modo `--preflight`: valida backup GH y configuraciones, sin sondeos OAuth.

Modo `--real-probe`: ejecuta DOS comandos `rclone lsf` de solo
lectura de medios sobre copias individuales 0600 y reporta únicamente
OK/AUTH/RATE_LIMITED/UNAVAILABLE/TAMPERED. El proveedor puede renovar
OAuth durante la prueba, pero la actualización queda en la copia
temporal eliminada al salir. No se usa ni altera el rclone.conf real,
el servicio systemd o los montajes. Después se releen la configuración
local y el SHA remoto para detectar cambios concurrentes.

    wget -q https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/develop/service.cloud.masqelec/tools/rclone_two_mount_real_probe_lab.py -O /tmp/rclone_two_mount_real_probe_lab.py
    python3 -m py_compile /tmp/rclone_two_mount_real_probe_lab.py
    python3 /tmp/rclone_two_mount_real_probe_lab.py --preflight
    python3 /tmp/rclone_two_mount_real_probe_lab.py --real-probe

No ejecutar el modo real sin conectividad. NO insertar ni cargar archivos
de credenciales reales en incidencias o respuestas; solo estados anónimos.

**Estas comprobaciones NO autorizan subir tokens MQC2.** La publicación
inmutable/condicional requiere una fase posterior de concurrencia y
confirmación operativa. La función strict_put es una pieza de transporte
desconectada; no se considera un publicador listo.

## Protección adicional antes de sondeo real (bloqueo operativo)

Los comandos rclone lsf pueden provocar una renovación de token ante
Microsoft. Incluso si los nuevos valores se guardan SOLAMENTE en una
copia privada, no podemos garantizar que el refresh_token anterior
mantenga validez para los montajes vivos del mismo usuario. La renovación
es un posible efecto de servidor, no solo de escritura local.

Por eso, el laboratorio se niega a ejecutar `--real-probe` si detecta
CUALQUIER proceso rclone mount en el dispositivo. También falla cerrado
si no puede inspeccionar /proc. Devuelve
`LAB_RESULT=BLOCKED_ACTIVE_MOUNTS` antes de solicitar el MQC2 o una
clave local. Esa comprobación cubre solo el dispositivo local y no
descarta montajes de CLIENTES remotos: todavía se requiere coordinación
de todos los escritores de cada cuenta.

El modo `--preflight` SÍ puede ejecutarse con los mounts activos,
porque lee el respaldo MQC2 de GitHub y compara estructura/SHA sin
hacer una petición OAuth a Microsoft. Se añadieron cuatro pruebas
adicionales del fence. Total esperado: **228**.

NO ejecutar `--real-probe` durante funcionamiento normal de Kodi.
No se realizará todavía un ensayo OAuth real en caliente.
