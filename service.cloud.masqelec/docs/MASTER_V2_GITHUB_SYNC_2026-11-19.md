# MASTER v2 — autocreación y reconciliación del MQC2 en GitHub

**Estado 19-11-2026: IMPLEMENTADO EN DEVELOP, AUTOPUBLICACIÓN DESACTIVADA, SIN PUBLICACIÓN REAL.**

Objetivo del operador: `service.cloud.masqelec` se actualizará en Kodi mediante el repositorio propio del operador; al activar los 2 FUSE + 4 bind, el MASTER mantendrá el fichero cifrado de recuperación más reciente para CLIENTES. Si GitHub no tiene archivo v2, el MASTER debe crearlo, y si los refresh de las fuentes reales han cambiado, debe actualizarlo. El operador publica el ZIP; no forma parte de esta tarea.

## Rutas y límites

| Sistema | GitHub `masQelec/cloud.masqelec`, rama `develop` |
|---|---|
| Legacy | `rclone/rclone.conf.crypt`: **no tocado** por sincronización v2 |
| V2 | `rclone/rclone-v2.conf.crypt`: **reservado, todavía no existe** |

La nueva ruta v2 utiliza el mismo contenedor autenticado **MQC2 ChaCha20-Poly1305** que ya soporta el addon. El candidato de MASTER contiene el inventario canónico de seis secciones, con las dos OneDrive actualizadas desde `/storage/.config/rclone/isolated-mounts/account1.conf` y `account2.conf`. Conserva los tokens y configuraciones de Google Drive del `rclone.conf` local canónico; no publica un `account*.conf` sin cifrar ni imprime credenciales.

## Qué se implementó

- `lib/rclone_two_mount_master_sync.py`: composición pura de dos snapshots privados, validación exacta crypt/cuenta/destino, clasificación `GET 404` (crear), `GET 200` (comparar) y errores. Un cambio únicamente de access token/expiry no desencadena subida. Actualización si cambia un refresh verificado, y bloqueo si cambian opciones estáticas.
- `lib/rclone_two_mount_master_runtime.py`: adaptador para GitHub `masQelec/cloud.masqelec` **solo** `develop` y **solo** `rclone/rclone-v2.conf.crypt`. GET autenticado de HEAD/contents, PUT con SHA previo para actualización y **sin SHA** para creación, nunca reintenta 409/422. Publicación cifrada, no plaintext.
- `rclone_token_sync.tick()`: rama MASTER v2 añadida bajo flags, con exclusión del camino legacy, intervalo de 60 segundos y log exclusivamente de estados predefinidos (nunca respuesta HTTP, token, remotename ni configuración). El CLIENTE v2 no publica.
- Fuente local: `stage._read_file(confidential=True)` exige archivo regular seguro 0600 y lectura estable. Los dos account configs son las fuentes OneDrive; el rclone.conf compartido conserva la configuración Google.
- Validación de credenciales: se exige `health_gate` con valor `ok` para cada remoto a publicar. En el adaptador operativo, esta puerta se implementa mediante sondeo rclone con **archivo temporal 0600 aislado** y sin mostrar stdout/stderr. **Puede renovar OAuth en la copia temporal** y nunca se ejecuta hasta activar flags tras las pruebas físicas.
- Antes de subir: segundo snapshot de las tres fuentes exactamente igual, HEAD de rama idéntico; después de subir: confirma SHA del blob cifrado, commit de PUT, lectura nueva de contents, descifrado/validación y HEAD estable. Si hay rotación local durante la publicación, devuelve `published_local_changed_requires_recheck` y no declara PASS; la siguiente ronda conciliará.
- Si GitHub responde 403, error de red, GET corrupto, identidad cambiada o permiso insuficiente: **NO interpretar como archivo ausente ni crear a ciegas**. Solo 404 observado en consulta autenticada con HEAD válido permite candidato de creación.
- La comparación con remoto detecta actualización cuando cambia el `refresh_token`. **La diferencia por sí sola no demuestra mayor frescura**: el MASTER se trata como única fuente autorizada y requiere sondas exitosas antes de promover cualquier valor. No resuelve automáticamente el control de otras aplicaciones OAuth fuera de rclone.

## Protecciones y estado

```text
MASTER_V2_GITHUB_SYNC_CODE=IMPLEMENTED
MASTER_V2_GITHUB_TRANSPORT=IMPLEMENTED_GATED
MASTER_V2_CREATE_ON_AUTHENTICATED_404=IMPLEMENTED_GATED
MASTER_V2_UPDATE_ON_VERIFIED_REFRESH_DIFF=IMPLEMENTED_GATED
MASTER_V2_CAS_READBACK=IMPLEMENTED_GATED
RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_STAGING_ENABLED=False
REAL_GITHUB_V2_FILE_CREATED=NO
REAL_OAUTH_V2_GITHUB_TEST=NOT_RUN
AUTO_CUTOVER=NOT_IMPLEMENTED
V2_CLIENT_OAUTH_RECOVERY=NOT_IMPLEMENTED
RELEASE_AUTHORIZED=NO
```

**MUY IMPORTANTE:** CI prueba la lógica y simuladores HTTP, no demuestra que el MASTER haya publicado correctamente en GitHub real ni que los refresh locales sean válidos. `rclone/rclone-v2.conf.crypt` NO existe todavía en cloud/develop. No se debe crear vacío o copiar directamente desde el legacy. El operador **no necesita ejecutar nada todavía** para esta función.

## Antes de habilitar la publicación

1. Terminar el cutover automático local en el primer arranque de Kodi, con rollback y retirada posterior de las cuatro unidades antiguas; verificar al menos una ruta real de cada cuenta sin interrumpir reproducción.
2. Verificar en el MASTER las fuentes `rclone.conf`, `account1.conf` y `account2.conf` y la compatibilidad del certificado/URL GitHub; evitar que los sondeos de copia temporal promocionen un refresh obsoleto.
3. Habilitar explícitamente **las tres banderas independientes** solo en release aprobada. Documentar la posibilidad de que un CLIENTE actualizado antes que el MASTER vea el archivo v2 todavía inexistente y siga con sus tokens locales.
4. Probar realmente: 404 autenticado → creación cifrada y readback; cambio verificado de una cuenta → PUT CAS con SHA y readback; sin cambios → ningún PUT; 409/422, error de red, 403, token OAuth inválido, HEAD concurrente y cortes de corriente → sin sustitución ciega.
5. Completar CLIENTE v2: descargar el MQC2 correcto **solo tras fallo AUTH confirmado**, validar identidad y aplicar únicamente a la cuenta afectada, con reinicio diferido del FUSE correspondiente. La descarga no modifica por sí sola los procesos rclone en memoria.

### Dos destinos y equipos no simultáneos

Los equipos Kodi antiguos no ejecutan las unidades v2. El MASTER con v2 deja de ejecutar el publicador legacy actual; por tanto, **el MQC2 legacy dejará de refrescarse** salvo que se implemente compatibilidad de publicación dual. Aunque la renovación de Microsoft no revoca automáticamente tokens previos, un CLIENTE antiguo que vuelva a conectarse mucho más tarde puede necesitar recuperación. **RIESGO RESIDUAL**: no declarar soporte de flota mixta indefinida sin escritor legacy v2 o política de caducidad. Esto no requiere dos arquitecturas activas en un mismo KodiELEC.

## Evidencia CI

`GitHub Actions` run [44421911947](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44421911947): **704/704 PASS**, Python 3.11. Nuevos tests sintéticos cubren creación en GET 404 con HEAD validado, 200 existente, cambios de OneDrive por cuenta, conservación Google, resultado 403 y errores de transporte, conflictos 409/422 no retry, recaptura tras PUT, cifrado, validación de lectura, identidad MASTER y gating de worker. El primer commit del adaptador falló por importar xbmc sin Kodi; ya corregido mediante importaciones diferidas y CI PASS.

**Siguiente fase**: implementar prueba de integración con cliente v2 y cutover de primera actualización; no publicar `cloud.masqelec` ni activar la función antes de eso.
