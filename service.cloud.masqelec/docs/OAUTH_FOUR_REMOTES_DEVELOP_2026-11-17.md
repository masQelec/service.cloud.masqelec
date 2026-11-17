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
- MASTER comprueba cada 30 minutos; tras publicar, deja un intervalo de
  al menos 6 horas entre publicaciones, siempre que Kodi no reinicie.
  El primer chequeo se permite inmediatamente tras iniciar el worker.
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
- El mantenimiento de Kodi protege CleanLibrary con _mounts_ready()
  (montajes FUSE presentes, accesibles y no vacíos), pero **esto no
  demuestra por sí solo que OAuth OneDrive funcione ahora**; un FUSE
  con datos en caché puede aparentar estar disponible. Es una posible
  mejora adicional del gate de limpieza, fuera de la activación OAuth.
- Si las bibliotecas son OneDrive Business/SharePoint, comprobar que la
  versión de rclone cumple requisitos desde 2027-04-01.

## Operaciones prohibidas en esta fase

- NO poner RCLONE_TOKEN_SYNC_ENABLED = True.
- NO subir credenciales durante el piloto.
- NO reemplazar el rclone.conf real durante el piloto.
- NO reiniciar automáticamente unidades de montaje.
- NO modificar main ni cloud.masqelec/master.

## Ensayo en KodiELEC (solo lectura)

Primero ejecutar el piloto actualizado sin simulación y confirmar:

LOCAL_ONEDRIVE_REMOTES=2
PUBLISHED_ONEDRIVE_REMOTES=2
LOCAL_GOOGLE_DRIVE_REMOTES=2
PUBLISHED_GOOGLE_DRIVE_REMOTES=2

Luego simular un CLIENTE inválido en configuración temporal:

python3 /tmp/rclone_oauth_pilot.py --simulate-client --remote-index 1
python3 /tmp/rclone_oauth_pilot.py --simulate-client --remote-index 2

Si hay RATE_LIMIT no repetir hasta que se normalice.

## Referencias

- https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens
- https://rclone.org/onedrive/
- https://rclone.org/docs/
