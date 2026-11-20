# P0-B / P0-D — generaciones OAuth y confirmación MQC2 tras CAS

**Fecha:** 17-11-2026 · **Rama:** `service.cloud.masqelec/develop` · **Estado:** solo laboratorio puro, no desplegado · **Pruebas:** 271/271 OK, GitHub Actions [44194785936](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44194785936).

## Contexto real que motiva el diseño

El operador confirmó que los cuatro procesos legacy de rclone renovaron los refresh OneDrive de `library_1` y `library_2` después de la última publicación MQC2. El segundo preflight KodiELEC identificó `ONEDRIVE_1=DIFFERENT`, `ONEDRIVE_2=DIFFERENT`, `DRIVE_1=SAME`, `DRIVE_2=SAME`, con autenticidad MQC2 y ajustes estáticos PASS. No se ha demostrado que un token esté revocado: **ni local ni GitHub pueden seleccionarse por antigüedad/expiry**.

Arquitectura futura: dos procesos rclone montando `users_library_1:` y `users_library_2:` (ambos wrappers `crypt`) sobre las cuentas OneDrive, más cuatro bind a las rutas Kodi originales. Sin cambios en las unidades existentes.

## Componentes añadidos en develop

### `lib/rclone_two_mount_generation.py` — P0-B

- `capture_window(canonical, accounts, remote, blob_sha, branch_head, epochs, remote_authenticated=True, cooperative_epochs=...)` toma una ventana **solo en memoria**, valida inventario (dos OneDrive + dos Drive) y conservación de `crypt`, y crea HMAC efímeros internos de las cuatro fuentes. **No imprimir ni persistir** las huellas ni el objeto.
- `epochs` representa (config canónica, config account1, config account2, respaldo MQC2), cada uno contador monotónico de escritor *cooperativo*; **no existen todavía tales contadores para rclone legacy**.
- `recheck_window(...)` distingue `changed_generation` (incluye ABA simulado), `changed_snapshot`, `changed_remote_blob`, `changed_remote_revision`, `blocked_untracked_writers`, `blocked_unverified_remote`, `blocked_invalid_sources`.
- `stable_for_lab_only` significa exclusivamente que una simulación con epochs declarados fiables es internamente consistente. **No habilita OAuth ni autorización de publicación**.
- Un A→B→A con bytes idénticos solo se detecta si el contador monotónico lo refleja. Un lector sin coordinación distribuida **no puede** detectar todo ABA remoto mediante un único HEAD GitHub. Requerimos un registro de generaciones de flota/fencing real.

### `lib/rclone_two_mount_readback.py` — P0-D parcial

- `confirm_readback` acepta exclusivamente datos entregados por quien haga en el futuro el PUT y dos consultas independientes de HEAD. No realiza red, no lee claves del dispositivo ni publica.
- Valida que el PUT figure como aceptado, que el HEAD leído durante el readback coincida con el commit publicado y permanezca estable, que el blob Git tenga el SHA esperado, que MQC2 autentique con clave correcta y que el **texto canónico descifrado** coincida byte a byte.
- Devuelve `verified_lab_only`, o un estado de bloqueo sin secretos. Un PUT 200/201 por sí solo **no confirma** datos ni coherencia con el resto de la flota.
- No equivale a readback operativo: la frescura e independencia de los GET/HEAD, la autorización del PUT, la identidad del escritor y la ausencia de un concurrente posterior son responsabilidad de protocolos aún no implementados.

## Validaciones comprobadas

| Control | Evidencia | Estado |
| --- | --- | --- |
| P0-B — cambio en cuenta 1/2, canónico, MQC2 y SHA/head | 20 pruebas nuevas, commit `5730c0e` | **PASS sintético** |
| P0-B — ABA A→B→A con contador fiable | Tests con epochs locales y remoto | **PASS sintético** |
| P0-B — escritores legacy no registrados | `blocked_untracked_writers` | **FAIL CLOSED** |
| P0-D — readback auténtico y SHA exacto | 12 pruebas nuevas, commit `d441ea5` | **PASS sintético** |
| P0-D — distinto nonce, cambio token, SHA incorrecto, clave errónea, movimiento HEAD | Bloqueos probados | **PASS sintético** |
| Suite consolidada Python 3.11 | [run 44194785936](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44194785936): `Ran 271 tests ... OK` | **PASS** |
| Contadores de generación fiables integrados con rclone | No existen en el montaje legacy | **NOT IMPLEMENTED** |
| Exclusión interdispositivo MASTER/CLIENTES | No existe coordinador global | **BLOCKED** |
| Transporte GitHub PUT + GET fresco + readback en producción | No integrado | **NOT RUN** |
| OAuth real `--real-probe` y 2 FUSE + 4 bind en KodiELEC | Prohibido/no autorizado | **NOT RUN** |

## Secuencia futura exigida (no ejecutable aún)

1. Inventariar todos los dispositivos con procesos OAuth; distinguir credenciales/grants por equipo y cuentas. Todo dispositivo legacy que renueve un token sin participar en el protocolo invalida cualquier supuesto de exclusión.
2. Definir propietario/epoch por cuenta e incrementar cada generación desde el mismo mecanismo que controla a **todos los escritores**, incluidos reinicios, procesos en segundo plano y clientes desconectados. Un lock Python **no controla rclone**. Los epochs actuales solo son simulaciones.
3. Leer la fuente local y MQC2 **autenticado**, congelar baseline con SHA del blob + commit GitHub y epochs **verificables**, preparar candidato sin tocar los mounts, validar identidad, `crypt` y Google Drive intactos.
4. Verificar de nuevo fuentes y generaciones antes de permitir cualquier acción; si una fuente cambió, bloquear. No elegir credencial por fechas.
5. Requerir autorización explícita por dispositivo y exclusión real de montajes que puedan renovar OAuth; no habilitar `--real-probe` con la flota en funcionamiento.
6. Solo en una futura versión operativa y autorizada: PUT único por SHA previo; `409/422` o resultados ambiguos **sin retry** ni promoción. Releer el commit publicado y el MQC2 autenticado con GET independiente, confirmar SHA/identidad/contenido, revalidar la flota y registrar la conclusión.
7. Separar del despliegue de unidades: `cloud/develop/system.d` se conserva legacy; migración 2 FUSE+4 bind solo después de un piloto reversible en rutas alternativas.

## Guardas que no se han cambiado

```text
RCLONE_TOKEN_SYNC_ENABLED=False
RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False
TWO_MOUNT_RELEASE_AUTHORIZED=NO
TWO_MOUNT_DEPLOY_EXECUTED=NO
TWO_MOUNT_LIVE_UNITS_CHANGED=NO
TWO_MOUNT_OAUTH_V2_PUBLISH_ENABLED=NO
```

Estos últimos marcadores son estado documental; los dos primeros son los flags reales. El repositorio `cloud/develop` no se ha escrito desde esta fase. No se han cambiado `addon/main`, `cloud/master`, secretos, tokens, unidades o montajes.

## Siguiente hito

**P0-C: diseñar y ensayar un protocolo de exclusión/coordinación OAuth MASTER–CLIENTES que se aplique también a quienes pueden refrescar tokens de Microsoft.** No llamar «resuelto» a P0-B/P0-D en producción; ambos son *lab pass / operational blocked*. La autorización final de release y las pruebas reales son independientes.
