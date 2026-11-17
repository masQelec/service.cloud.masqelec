# OAuth de cuatro remotos (develop) — revisión 2026-11-17

## Configuración constatada

- Dos remotos de tipo onedrive: bibliotecas multimedia, críticos.
- Dos remotos de tipo drive: actualización y registros, secundarios.
- Cuatro unidades de montaje systemd usan /storage/.config/rclone/rclone.conf.
- El MASTER publica en cloud.masqelec/develop/rclone/rclone.conf.crypt.
- main y cloud.masqelec/master quedan fuera del alcance.

## Hallazgos del código anterior

1. oauth_tokens() seleccionaba solo Google Drive. OneDrive quedaba excluido.
2. _AUTH_IDENTITY no incluía drive_id ni drive_type; el arranque podría
   conservar un token local al cambiar la identidad de una unidad OneDrive.
3. El criterio de "token antiguo" usaba el vencimiento de access_token,
   que no permite ordenar versiones de refresh_token.
4. master_should_publish() admitía subir cambios de opciones estáticas.
5. El sondeo cliente pasaba rclone.conf activo a un proceso rclone adicional:
   podía renovarlo mientras otros montajes lo estaban escribiendo.
6. Se comunicaba recovered aunque los procesos rclone mount ya activos
   pueden seguir con su token en memoria. No hay reinicio seguro implementado.
7. El primer chequeo de tick dependía del uptime de la máquina, no del
   inicio del trabajador.
8. Con OneDrive, subir cada rotación normal implicaría demasiados commits.

## Política corregida en develop

- Tipos admitidos: drive y onedrive (excluido box, etc.).
- Se preserva el token local solo con coincidencia de identidad:
  type, client_id, client_secret, scope, drive_id, drive_type,
  root_folder_id, tenant, tenant_url, tenant_api_version, region,
  auth_url, token_url, y claves históricas.
- MASTER publica **solo** cuando cambia algún refresh_token y no hay
  cambios efectivos de opciones no-token ni de inventario de remotos.
- Verifica cada remoto modificado con rclone usando una configuración temporal.
  No ordena tokens por el expiry del access_token.
- MASTER inspecciona la huella local cada 60 segundos (sin enviar
  secretos ni consultar GitHub cuando el refresh_token no cambia).
  Publica en GitHub **cada refresh_token nuevo** detectado y que supere
  la comprobación del remoto en una copia temporal.
  No se impone un bloqueo de 6 horas a nuevas publicaciones.
- Si el archivo acaba de ser escrito por rclone, deja 10 segundos para
  estabilizarse y lo reintenta el siguiente minuto.
- Si la huella local no cambia, hace conciliación con GitHub cada 6 horas;
  no se crean commits por cambios de access_token ni expiry.
- La latencia máxima normal para detectar una rotación es de ~1 minuto
  mientras el worker esté en ejecución y haya red; no hay hook directo
  dentro del proceso rclone mount.
- CLIENTE comprueba cada hora una copia privada del fichero. Si falla
  explícitamente OAuth, descarga y valida MQC2, fusiona solo el token
  fallido, comprueba el candidato, vuelve a leer el activo y lo reemplaza
  atómicamente tras crear copia de seguridad.
- En arranque, si cambia la identidad de alguna unidad OneDrive, no se
  reemplaza el conf local ni se actualizan unidades systemd; revisión manual.
- Errores 429, cuota, 403, permisos, red y TLS no sustituyen tokens.
- Si se recupera en disco, el estado advierte que los montajes podrían
  requerir reinicio. **No reinicia unidades mientras hay reproducción.**
- Ningún token ni contenido de rclone.conf se registra.

## Límites pendientes antes de habilitar

- Prueba real con ambos OneDrive usando tools/rclone_oauth_pilot.py.
  Índices 1 y 2: OneDrive; 3 y 4: Google Drive.
- Confirmar dos remotos por proveedor en local y en GitHub.
- Prueba controlada en CLIENTE real con copias temporales.
- Diseñar reinicio controlado de cada montaje solo cuando Kodi esté
  sin reproducción, con rollback si falla.
- Comprobar escrituras concurrentes de varios rclone mount al mismo conf:
  read_stable y reread reducen riesgos, pero no implementan bloqueo
  compartido con procesos externos.
- Los procesos rclone mount guardan sus tokens en memoria y escriben
  sus propias renovaciones. La comprobación en copia temporal puede
  provocar una renovación adicional independiente; el archivo publicado
  corresponde a la última instantánea estable del MASTER, no a una
  supuesta fecha de creación de refresh_token.
- El MASTER incorpora autorrecuperación desde la reserva MQC2:
  * Corrupción estructural: dos observaciones iguales separadas por 60 s,
    descarga de reserva, exige exactamente 2 OneDrive y 2 Google Drive
    completos y valida con rclone ambos OneDrive y los Google Drive.
    Se admite un RATE_LIMIT explícito de Google Drive (servicio secundario)
    si ambos OneDrive funcionan; cualquier fallo de OneDrive o un AUTH
    de Google Drive bloquea la restauración completa.
  * Fallo OAuth explícito: sondeo de OneDrive cada 15 min y Google Drive
    cada 60 min, sustituyendo solo el token que falla tras verificar copia.
  * Nunca se recupera por error de red, cuota, permisos o rate-limit.
  * Una identidad OneDrive diferente (drive_id/drive_type) bloquea reemplazo.
  * El fichero previo se guarda en backup privado único 0600; cambio atómico.
  * Si la comprobación falla se conserva el archivo actual, incluso dañado;
    no se ejecutan reinicios de montajes FUSE ni cambios de producción.
  * Si GitHub o la clave no están disponibles, no puede autorrecuperarse.
- Límite de concurrencia: aunque se compara antes del reemplazo, los procesos
  rclone mount aún podrían escribir en el intervalo de la operación atómica;
  no hay locking interproceso compartido. Requiere prueba real controlada.
- La recuperación ocurre cuando arranca el worker; el flujo cloud_storage
  de arranque se ejecuta antes y no queda sustituido por este mecanismo.
- El mantenimiento de Kodi protege CleanLibrary con _mounts_ready()
  (montajes FUSE presentes, accesibles y no vacíos), pero **esto no
  demuestra por sí solo que OAuth OneDrive funcione ahora**; un FUSE
  con datos en caché puede aparentar estar disponible. Es una posible
  mejora adicional del gate de limpieza, fuera de la activación OAuth.
- Si las bibliotecas son OneDrive Business/SharePoint, comprobar que la
  versión de rclone cumple requisitos desde 2027-04-01.

## Operaciones prohibidas en esta fase

- NO poner RCLONE_TOKEN_SYNC_ENABLED = True.
- **NO activar el worker por haber superado solo pruebas sintéticas**;
  simular corrupción en una copia aislada y ejecutar pruebas en MASTER real
  sin modificar rclone.conf hasta completar la validación.

- NO subir credenciales durante el piloto.
- NO reemplazar el rclone.conf real durante el piloto.
- NO reiniciar automáticamente unidades de montaje.
- NO modificar main ni cloud.masqelec/master.

## Ensayo en KodiELEC (solo lectura)

**No usar el piloto antiguo suelto en /tmp**: podría importar la política
antigua desde el addon instalado y omitir ambos OneDrive.

Descargar y ejecutar tools/rclone_oauth_lab_setup.sh en KodiELEC.
El script crea /tmp/masqelec-oauth-lab con los módulos del commit fijado,
sin instalar código en el addon y sin modificar el conf activo.

Usar:

python3 /tmp/masqelec-oauth-lab/tools/rclone_oauth_pilot.py

Confirmar:

LOCAL_ONEDRIVE_REMOTES=2
PUBLISHED_ONEDRIVE_REMOTES=2
LOCAL_GOOGLE_DRIVE_REMOTES=2
PUBLISHED_GOOGLE_DRIVE_REMOTES=2

Luego simular un CLIENTE inválido en configuración temporal:

python3 /tmp/masqelec-oauth-lab/tools/rclone_oauth_pilot.py --simulate-client --remote-index 1
python3 /tmp/masqelec-oauth-lab/tools/rclone_oauth_pilot.py --simulate-client --remote-index 2

Si hay RATE_LIMIT no repetir hasta que se normalice.

## Referencias

- https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens
- https://rclone.org/onedrive/
- https://rclone.org/docs/

## Ensayo de autorrecuperación MASTER con respaldo real (solo /tmp)

La suite local de regresión pasó 100/100 en Ubuntu (informado por operador,
2026-11-17). Falta validación de integración en KodiELEC.

El script tools/master_oauth_recovery_lab.py descarga únicamente módulos Python
del commit fijo c3d1fa5 de develop a un directorio privado de /tmp; descarga
el respaldo MQC2 ya existente desde cloud/develop y crea una copia de
rclone.conf de laboratorio con un token JSON sintéticamente corrupto.
No edita el conf activo, el addon, servicios ni GitHub.

Ejecución en KodiELEC tras descargar el script al directorio /tmp:

    python3 /tmp/master_oauth_recovery_lab.py

Busca CORRUPTION_FIRST_CHECK=master_corrupt_pending,
CORRUPTION_SECOND_CHECK=master_recovered_restart_pending, BACKUP_ISOLATED_0600=PASS,
RESTORED_LAYOUT=PASS y LAB_RESULT=PASS. En RATE_LIMIT o
master_candidate_unverified el ensayo es inconcluyente y el archivo real
permanece intacto. No repetir de inmediato contra Microsoft/Google.
Un éxito con lsf prueba el acceso actual, no necesariamente la posibilidad
de renovar un refresh_token que caduque en el futuro.

## Diagnóstico 2026-11-17: dos secciones extra

El laboratorio MASTER detectó LOCAL_SECTIONS=6, LOCAL_OAUTH_REMOTES=4,
LOCAL_ONEDRIVE=2, LOCAL_GOOGLE_DRIVE=2 y LAB_FAILED_AT=VALIDATE_LOCAL_LAYOUT.
El fallo era la condición errónea len(config)==4, no una prueba de
corrupción. El MASTER exige exactamente 2 OneDrive + 2 Google Drive con
token válido, pero **permite secciones auxiliares no OAuth** (por ejemplo
alias, crypt, local). Se mantienen las secciones auxiliares en todo
rclone.conf restaurado o publicado.

La reserva publicada puede contener también las dos secciones adicionales,
pendiente de corroborar con el laboratorio actualizado. Si los nombres,
tipos o parámetros estáticos de secciones auxiliares difieren del archivo
actual, la recuperación completa debe bloquearse, sin eliminar secciones
ni modificar la configuración operativa.


## Validación tras soporte de seis secciones

Las 100 pruebas previas no cubrían secciones auxiliares: se añadieron
11 pruebas (8 de política y 3 del worker). Total previsto: 111.
La integración del MASTER exige exactamente cuatro OAuth válidos (dos
OneDrive, dos Google Drive), pero admite otras secciones sin token OAuth.
El laboratorio informa también LOCAL_AUXILIARY_SECTIONS y
GITHUB_AUXILIARY_SECTIONS; no se publican nombres ni parámetros.
La prueba real debe confirmar que las secciones adicionales coinciden
entre MASTER y GitHub. En caso contrario, informar
BLOCKED_DIFFERENT_REMOTE_IDENTITIES y no restaurar ni publicar.

## Fence de concurrencia con rclone mount (2026-11-17)

Los cuatro servicios systemd del cloud/develop utilizan el mismo
`/storage/.config/rclone/rclone.conf` (cada uno con `--config`).
Rclone guarda tokens renovados mediante un temporal y renombrados, sin
cooperar con un `threading.Lock` del addon. Un `os.replace` local no
es un compare-and-swap interproceso y puede perder una escritura de rclone.

Guardas del worker:

- Inspección read-only de `/proc/*/cmdline` para localizar procesos
  `rclone mount` que usen exactamente `CONF_PATH`. Los mounts sin
  `--config` se tratan conservadoramente como posibles escritores.
- MASTER y CLIENT no sustituyen `rclone.conf` si detectan mounts activos
  sobre el mismo archivo. Devuelven `mounts_active` y reintentan al próximo
  ciclo. No detienen servicios, ni interrumpen reproducción.
- Se compara la **generación** (dev/inodo/tamaño/mtime_ns/ctime_ns) y los
  bytes antes de instalar y otra vez justo antes del reemplazo. Así se
  detectan renovaciones que incluso escriban los mismos bytes y reemplazos
  durante la validación. La comprobación **no es atómica con os.replace**.
- La publicación MASTER sigue funcionando durante los montajes porque
  únicamente **lee** el archivo. Si el local rota durante el upload,
  devuelve `published_local_advanced` y no memoriza esa publicación como
  sincronización final. El siguiente minuto volverá a conciliar.
- Sin confirmación del estado de `/proc`, se bloquea la sustitución.

**Limitación deliberada:** con cuatro `rclone mount` permanentes no puede
haber recuperación en caliente del archivo compartido mediante el worker.
No activar la bandera hasta diseñar mantenimiento/remontaje seguro o aislar
la escritura de tokens. El fence es la mitigación más segura sin cambiar
systemd ni interrumpir Kodi; no equivale a locking compartido real.

La documentación oficial describe el guardado con temporal y cambios de
nombre: https://rclone.org/docs/#config-string. En los servicios
`cloud.masqelec/develop/system.d` no hay un mecanismo de lock interproceso.

Pruebas previstas tras este cambio: 123 (111 anteriores + 12 de concurrencia).
