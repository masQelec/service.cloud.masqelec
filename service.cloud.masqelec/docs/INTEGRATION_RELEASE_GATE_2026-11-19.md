# Gate integrado — actualización automática 4 FUSE → 2 FUSE + 4 bind
**Revisión de código 19/11/2026. Estado: NO RELEASE. Rama develop solamente.**

## Resultado de la auditoría agrupada

| Subsystem | Implementado en develop | Evidencia real | Condición para release |
|---|---|---|---|
| Unidades systemd: 2 FUSE + 4 binds | Sí, generador y laboratorio | MASTER: `PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL`, `CLEANUP=COMPLETE` | Validar unidades permanentes y reboot |
| STRM / rutas Kodi | Rutas antiguas preservadas en plan | Prueba de lectura local FUSE ficticio | Dos muestras .strm locales por dispositivo y lectura real tras cutover |
| Auto primer arranque | `rclone_two_mount_autostart.tick` conectado a `service.py` | CI simulado | Ensayo físico con Kodi idle/reproducción, corte y retry |
| Rollback y crash | Snapshot privado/journal/guards/drop-ins | Pruebas sintéticas | Corte físico, reboot, rollback y reanudación |
| Limpieza de las cuatro unidades legacy | `rclone_two_mount_legacy_cleanup.py` | CI simulado | Prueba de retirement/reboot/downgrade sobre KodiELEC |
| MASTER publica MQC2 v2 | Adaptador `master_runtime.py` y CAS | CI simulado | 404→crear, readback, cambios refresh, concurrencia y fallos reales |
| CLIENTE recupera OAuth v2 | **NO conectado** como recuperación por cuenta desde `rclone-v2.conf.crypt` | Ninguna | Implementar AUTH comprobado, identidad, reconciliación privada, restart diferido y rollback |
| Flota mixta | Endpoints separados legacy/v2 | Sin prueba conjunta | Evitar que clientes legacy dependan de MQC2 legacy congelado tras pasar MASTER a v2 |

## Hallazgos de seguridad

- `constants.py` conserva en `False` FIRST_RUN, FEATURE_ALLOWED, ROLLBACK_GATE_PASSED, LEGACY_RETIRE, AUTO_RECOVERY, MASTER_SYNC, TOKEN_SYNC y STAGING. No cambiar todos a True como atajo.
- La primera transición no comienza si Kodi reproduce o si no descubre dos rutas .strm confiables; la lectura de medios tras cutover está acotada.
- El `PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL` solo abarca fixtures locales. No demuestra autenticación OAuth ni estabilidad de OneDrive o recuperación tras reboot.
- El fallo `ExecStartPre` anterior estaba ligado a `/bin/test` ausente según la documentación histórica y fue corregido usando `[ -d ... ]`. El nuevo diagnóstico añadido en el script no constituye otra corrección de montaje.
- Activar auto migración antes de implementar recuperación CLIENTE introduce pérdida de servicio ante tokens expirados aunque el montaje local inicial funcione.
- Kodi puede actualizar los addons en momentos distintos: la coexistencia de *versiones en distintos equipos* sigue siendo inevitable aunque en cada equipo no coexistan las arquitecturas de montaje.
- El addon incluye material de credenciales cifrado bajo `constants.py`: no exponer estas constantes en informes públicos ni pruebas; revisar gestión de secretos antes de publicación.

## Próximo gate físico, sin escritura

Preflight de descubrimiento de medios `rclone_two_mount_media_samples.py --inventory` en al menos MASTER y un CLIENTE representativo. Descarga por SHA fijado, `py_compile`, ejecución sin permisos de migración. Debe devolver `MEDIA_DISCOVERY_RESULT=PASS_2_LOCAL_STRM_ACCOUNTS`, o quedar bloqueado con diagnóstico. No imprimir rutas ni contenidos.

## Gate indispensable antes de una release

1. Implementar y probar CLIENTE v2 para error OAuth auténtico por cuenta; no reemplazar el rclone.conf compartido ni interpretar red/cuota como AUTH.
2. Probar secuencias de upgrade, parada de unidades legacy, recovery ante cortes, cold boot, Kodi reproduciendo, reinicio del addon y downgrade, en banco no productivo.
3. Probar MASTER v2 con transporte GitHub real y CAS/readback cifrado, permisos mínimos y comprobación de fuentes.
4. Probar nodo legacy encendido después de MASTER v2; decidir estrategia explícita para MQC2 legacy y documentación de límites.
5. Ejecutar tests Python+GitHub Actions sobre commit final y conservar los logs de PASS. El último 773/773 anterior no valida nuevos commits.
6. Solo después, revisión de configuración por el operador y autorización de publicación del ZIP. Este documento **NO** autoriza despliegue.

## Prohibiciones activas

`RELEASE_AUTHORIZED=NO`
`ONEDRIVE_REAL_CUTOVER_VERIFIED=NO`
`REAL_REBOOT_RECOVERY_VERIFIED=NO`
`CLIENT_V2_OAUTH_RECOVERY_IMPLEMENTED=NO`
`CLOUD_V2_FILE_PUBLISHED=NO`
`PRODUCTION_UNITS_CHANGED=NO`

No subir `rclone.conf`, refresh tokens, keys, secreto del MASTER, trazas HTTP ni rutas personales.

## Avance integrado CLIENTE v2 — 19/11/2026

- Nuevo módulo **puro, sin IO** `lib/rclone_two_mount_client_recovery.py`. Exige autorización exacta y error `auth` confirmado para una cuenta (0/1); estado HTTP 200 del fichero v2, dos HEAD autenticados estables, descifrado MQC2+SHA y validación de estructura/identidad.
- Conserva el canónico y modifica lógicamente el token de **una sola cuenta** en una copia candidata; compara las opciones no OAuth del account conf y devuelve candidato solo como `candidate_requires_probe`. Si GitHub da 404, 403, error, contenido corrupto o token igual, **bloquea sin fallback legacy**.
- `confirm_probe` exige prueba `ok`, generaciones local y remoto estables; **no instala ni reinicia**. Pruebas nuevas: `tests/test_rclone_two_mount_client_recovery.py`.
- Commits del motor y pruebas: `fd6dd00e5efb6ed0d071ec049b4cadc91d6044ac`, `30b39dc8af93d18fccbcb32721ca4f25c2926e3f`.
- **Pendiente**: validación CI de estos commits, adaptador operativo autenticado de descarga, sondeo con temporal 0600, actualización atómica del account conf y reinicio diferido del FUSE afectado, snapshots, rollback y prueba real de fallo OAuth. La fase añadida no equivale a recuperación CLIENTE finalizada.
- MASTER: el usuario confirmó `MEDIA_DISCOVERY_RESULT=PASS_2_LOCAL_STRM_ACCOUNTS` en KodiELEC, con ambas muestras FOUND, sin OneDrive, OAuth ni systemd; CLIENTES pendientes.

`CLIENT_V2_OAUTH_RECOVERY_PLANNER=IMPLEMENTED_GATED`
`CLIENT_V2_OAUTH_RUNTIME=NOT_IMPLEMENTED`
`CLIENT_V2_RECOVERY_TESTS_CI=NOT_CONFIRMED`
`RELEASE_AUTHORIZED=NO`
