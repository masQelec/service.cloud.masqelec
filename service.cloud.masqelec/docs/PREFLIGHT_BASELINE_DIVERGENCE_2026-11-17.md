# Cloud masQelec — preflight MQC2 con refresh divergente

**Fecha:** 17-11-2026 · **Máquina:** KodiELEC MASTER · **Clasificación:** Seguridad / P0-A · **Estado:** BLOCKED, sin corrección automática.

## Evidencia recibida

```text
LAB_MODE=TWO_MOUNT_OAUTH_V2_GITHUB_SHA_AND_PROBE
CODE_REF=636866996cd72551ef37eb4439c6f023d5c3561d
LIVE_CONFIG_WRITE=NO
MOUNT_RESTART=NO
SYSTEMD_WRITE=NO
GITHUB_UPLOAD=NO
OAUTH_PROBE_REQUESTED=NO
MASTER_CANONICAL_LAYOUT=PASS
GH_BLOB_SHA_VALID=PASS
MQC2_AUTHENTICATED=PASS
GH_STATIC_IDENTITY=PASS
GH_OAUTH_BASELINE=DIFFERENT
LAB_RESULT=BLOCKED_BASELINE_DIVERGED
```

El fichero local y el respaldo MQC2 GitHub son estructuralmente compatibles y el MQC2 se ha autenticado. **Al menos un refresh_token entre los 4 OAuth (2 OneDrive y 2 Google Drive) difiere.** No prueba caducidad, validez ni orden cronológico. La respuesta del programa es de seguridad: no selecciona origen, no consulta OAuth a proveedores, no restaura y no publica.

## Instrumentación para identificación sin secretos

El script del commit `07b008db93ad524e9cbfec5b5e0e4b63704fe15e` añade estos marcadores de diagnóstico:

```text
BASELINE_REFRESH_ONEDRIVE_1=SAME|DIFFERENT
BASELINE_REFRESH_ONEDRIVE_2=SAME|DIFFERENT
BASELINE_REFRESH_DRIVE_1=SAME|DIFFERENT
BASELINE_REFRESH_DRIVE_2=SAME|DIFFERENT
GH_BRANCH_COMMIT_STABLE=YES
LIVE_CONFIG_CHANGED=NO
REAL_OAUTH_PROBE=NOT_EXECUTED
GITHUB_PUBLISH_ALLOWED=NO
LAB_RESULT=BLOCKED_BASELINE_DIVERGED
```

Los signos `|` en este ejemplo indican valores posibles, no salida literal. El orden OneDrive sigue los wrappers `users_library_1` y `users_library_2`, pero esos nombres **no se imprimen**; los Drive se ordenan por sección. No registrar valores ni hashes de refresh.

Antes de informar diferencias, el script relee la configuración local y compara el HEAD remoto `cloud/develop`: si cualquiera cambia, el resultado pasa a `INCONCLUSIVE`. La rama remota se usa por commit fijo para leer MQC2 autenticado. La comprobación de HEAD no sustituye un bloqueo distribuido, no detecta necesariamente todos los ciclos ABA de referencias ni garantiza cuál refresh funciona.

## Comandos para repetir exclusivamente el diagnóstico de lectura

```bash
wget -q 'https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/07b008db93ad524e9cbfec5b5e0e4b63704fe15e/service.cloud.masqelec/tools/rclone_two_mount_real_probe_lab.py' -O /tmp/rclone_two_mount_real_probe_lab.py
python3 -m py_compile /tmp/rclone_two_mount_real_probe_lab.py
python3 /tmp/rclone_two_mount_real_probe_lab.py --preflight
```

**No ejecutar `--real-probe`.** Si vuelve a producir `BLOCKED_BASELINE_DIVERGED`, guardar solo los marcadores no sensibles y detenerse. No publicar `rclone.conf`, credenciales, JSON OAuth, claves ni capturas de secretos. No usar `rclone config reconnect`, `rclone lsf` contra OAuth ni herramientas que puedan renovar tokens. No detener/reiniciar montajes. No editar `cloud/develop/system.d`.

## Validación del desarrollo

- Commits de diagnóstico: `f1c6ba1` (script), `20f924c` (pruebas de reporte), `07b008d` (dos tests end-to-end del preflight con MQC2 ficticio y cambio de HEAD).
- CI `develop`: `Ran 239 tests ... OK` / GitHub Actions run [44191814025](https://github.com/masQelec/service.cloud.masqelec/actions/runs/44191814025).
- El resultado 239/239 corresponde a pruebas sintéticas. **Este nuevo script todavía NO tiene salida de KodiELEC real.**
- Gates: `P0-A=BLOCKED`; `RCLONE_TOKEN_SYNC_ENABLED=False`; `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`; `NO_DEPLOY=YES`; `LIVE_MOUNT_CHANGE=NO`; `GITHUB_CREDENTIAL_UPLOAD=NO`.

## Siguiente diagnóstico / decisión

1. Identificar si difiere OneDrive 1, OneDrive 2, Drive 1 y/o Drive 2.
2. Mantener las dos copias intactas y examinar la secuencia de renovación documentada y el estado de los montajes **sin solicitar un refresh OAuth**.
3. Diseñar coordinación MASTER–CLIENTES y generaciones antes de autorizar cualquier recuperación controlada.
4. Un `DIFFERENT` no determina qué token reemplazar. Cualquier paso con escritura o proveedor OAuth real requiere análisis adicional y permiso operativo específico.
