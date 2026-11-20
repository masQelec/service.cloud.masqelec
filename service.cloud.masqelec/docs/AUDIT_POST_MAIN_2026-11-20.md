# Auditoría post-integración main — 20/11/2026

## Alcance y línea base

Repositorios: `masQelec/service.cloud.masqelec` (`main` integrado por
PR #1, merge `50121d0`; desarrollo de endurecimiento en `develop`).
Addon 2.3.2 sobre CoreELEC/Kodi. MASTER y CLIENT piloto han validado
2 FUSE + 4 bind, retirada de legacy y OneDrive aislado del `rclone.conf`.
Reinicio CLIENT validado previamente sobre 2.3.1; la recuperación de
credenciales tras una revocación real **no está probada**.

Módulos revisados: `service.py`, `rclone_token_sync.py`,
`rclone_two_mount_client_worker.py`,
`rclone_two_mount_client_runtime.py`,
`rclone_two_mount_client_apply.py`,
`rclone_two_mount_client_early_boot.py`,
`rclone_two_mount_master_runtime.py`,
`rclone_two_mount_master_sync.py`,
`rclone_two_mount_config_split.py`,
`rclone_two_mount_verify.py`,
`rclone_two_mount_autostart.py`,
`rclone_two_mount_boot_install.py`,
`rclone_token_policy.py`, sus tests y CI. Esto es una **auditoría focalizada**,
no una revisión exhaustiva de todas las rutas del addon.

## Hallazgos

### H1 — Alta — Sondas de OAuth y generaciones de refresh_token

`rclone_token_sync._probe` ejecuta `rclone lsf` con una configuración
temporal 0600. En `client_worker._auth_state` se ejecuta
`_probe_private` y se **ignoran los bytes post-probe** cuando la cuenta
parece sana. El proceso de sondeo puede renovar credenciales en una copia
privada sin sincronizarlas con el writer activo `account*.conf`.
Microsoft puede tolerar tokens anteriores, por lo que no afirmamos que
toda renovación rompa el servicio. El riesgo real es divergencia entre
generaciones sin un protocolo de reconciliación durable.

El MASTER realiza otra sonda en copia temporal antes de publicar MQC2.
Se ha implementado una **mitigación parcial en develop**:
`master_runtime._probe_candidate` vuelve a leer la copia y rechaza
el resultado para cualquier remoto cuyo refresh_token haya cambiado,
y para todos los remotos si han cambiado las opciones estáticas o el
inventario. Así no se publica como válido un refresh anterior a una
rotación en la propia prueba. Esto no repara la coordinación con el
writer FUSE. Seguimiento: [issue #2](https://github.com/masQelec/service.cloud.masqelec/issues/2).
Pruebas sintéticas: rotación, options tamper, credencial intacta.

**Gate pendiente:** diseñar un flujo que no descarte una renovación válida;
ensayar carrera entre FUSE y sonda con dos cuentas, journal, pérdida de
respuesta, reboot, caída GitHub y rollback. No revocar tokens reales.

### H2 — Media — Sin CI para cambios directos en main

El workflow anterior `.github/workflows/develop-tests.yml` solo
respondía a pushes de `develop`. La integración de PR #1 en `main`
se realizó con pruebas verdes en `develop`, pero no una suite CI
independiente en el commit combinado. En `develop` se ha ampliado la
matriz a pushes en `develop` y `main`, manteniendo sin despliegue
ni acceso Kodi/OneDrive. Una vez integrado, validar un run real en `main`.

### H3 — Media — Separación dev/estable del repositorio cloud

`constants.CLOUD_BRANCH`, `master_runtime.BRANCH` y las rutas MQC2
v2 están fijadas a `develop` incluso con código que ya vive en
`main`. Este comportamiento es coherente con los ensayos actuales,
pero **main no es todavía un canal de configuración independiente**.
No cambiar `CLOUD_BRANCH` por simple renombrado: requiere publicar
y verificar artefactos `cloud/main`, permisos y compatibilidad
de MASTER/CLIENT.

### H4 — Media — Escritura concurrente de la configuración general

`config_split.retire_once` lee una generación del fichero y la
recomprueba inmediatamente antes de `os.replace`. Esta comprobación
reduce carreras, pero el par comparar/reemplazar no es una operación
atómica de tipo CAS con otro escritor rclone que pueda actualizar
Google Drive. Ocurre únicamente al limpiar el fichero general por
primera vez; los pilotos ya pasaron. No repetir forzadamente la limpieza.
Considerar un lock/exclusión con escritores de Google Drive en una
revisión específica antes de futuras migraciones de formato.

## Cambios implementados en develop

- Workflow Python 3.11 se dispara también en `main` tras su integración.
- `master_runtime._probe_candidate` comprueba el resultado real del
  sondeo y bloquea publicación de refresh_token de generación anterior
  si la propia sonda lo rota.
- Tres tests sintéticos añadidos, sin Kodi, OneDrive ni archivos reales.

## Resultado y límites

GitHub Actions sobre `develop`: **960 tests OK** tras los cambios de
endurecimiento (run 44813956983). No se ha ejecutado prueba OAuth real
contra Microsoft, prueba de corte físico ni prueba del paquete distribuido
con este código nuevo. **Mantener addon.xml en v2.3.2 mientras estos cambios
no se publiquen en Kodi; el endurecimiento es código aún de desarrollo.**

Siguiente tarea: diseñar/probar coordinación OAuth por cuenta y resolver
la estrategia `cloud/main` antes de habilitar nuevas actualizaciones
automáticas masivas.
