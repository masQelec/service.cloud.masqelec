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

## Continuación: CLIENTE v2 — coordinador de verificación (19/11/2026)

Añadido `lib/rclone_two_mount_client_runtime.py::verify_once`, con callbacks explícitos de lectura local, HEAD autenticado, GET del endpoint v2 y sondeo OAuth de candidato, **sin escritura de credenciales, montaje ni `systemctl`**. El procedimiento rechaza autorización falsa, falta de error `auth`, índice de cuenta inválido, dependencias ausentes, GET no exitoso, identidad incompatibile, cambio de HEAD, prueba fallida y cambios de fuentes locales. Relee las fuentes y HEAD tras el probe.

Se ha endurecido `rclone_two_mount_client_recovery.prepare` con comparación de opciones no OAuth del canónico remoto y validación de cuenta aislada mediante `rclone_two_mount_oauth._account`. Pruebas regresivas en `test_rclone_two_mount_client_recovery.py` y `test_rclone_two_mount_client_runtime.py`.

El estado `probe_verified_requires_transactional_install` **no autoriza escritura**. Falta implementar un ejecutor real protegido mediante lock local durable, snapshot, instalación atómica 0600 bajo control de escritor rclone, reinicio del FUSE de la cuenta afectada, verificación de medio y rollback físico. Los callbacks `head/get/probe` aún requieren integración operativa, configuración segura e inyección desde el worker.

**CI no confirmado para los últimos commits**. No existe validación en KodiELEC real del nuevo coordinador. No activar las banderas. No crear todavía `rclone-v2.conf.crypt` en cloud sin pasar los gates MASTER.

`CLIENT_V2_VERIFICATION_ORCHESTRATOR=IMPLEMENTED_GATED`
`CLIENT_V2_TRANSACTIONAL_INSTALL=NOT_IMPLEMENTED`
`CLIENT_V2_RUNTIME_CONNECTED_TO_ADDON=NO`
`LATEST_CI_RESULT=NOT_CONFIRMED`
`RELEASE_AUTHORIZED=NO`

## CLIENTE v2: protocolo transaccional inyectable (19/11/2026)

Nuevos archivos:
- `lib/rclone_two_mount_client_transaction.py`: motor por cuenta con autorización explícita, prueba validada, Kodi idle, snapshot durable exigido antes de detener la cuenta, fencing de escritor, revalidación local, instalación, arranque, salud, confirmación y rollback ante cualquier fallo. Rechaza adaptadores incompletos. Nunca toca por sí mismo filesystem, systemd ni OAuth.
- `tests/test_rclone_two_mount_client_transaction.py`: casos de camino feliz simulado, autorización bloqueada, reproducción activa, snapshot fallido, cada etapa fallida, rollback incompleto y candidato manipulado.

**Advertencia de alcance:** `RECOVERED_VERIFIED` significa que **callbacks inyectados devolvieron True**, no que haya un rclone real reiniciado. No existe todavía un adaptador que garantice exclusión de escritores de rclone, journal físico de CLIENTE, instalación 0600, recuperación tras apagón y prueba post-arranque. No conectar este módulo al worker ni permitir que un FakeOps pase a producción.

**Validación no acreditada:** el proveedor de consulta GitHub no muestra workflow/status asociado al commit nuevo; un intento de clonación desde el entorno disponible falló por DNS. No afirmar que la suite pasó.

`CLIENT_V2_TRANSACTION_PROTOCOL=IMPLEMENTED_GATED`
`CLIENT_V2_PHYSICAL_ADAPTER=NOT_IMPLEMENTED`
`CLIENT_V2_CRASH_RECOVERY=NOT_VERIFIED`
`CI_NEW_COMMITS=NOT_VERIFIED`
`RELEASE_AUTHORIZED=NO`

## Regresión Ubuntu confirmada por operador — 19/11/2026

Tras corregir el test de permisos `kodi.service.d` en el commit `50ca2b6d1a8c6b1724050c21a249aec3bcf2094f`, el operador ejecutó en Ubuntu `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'` y obtuvo **Ran 864 tests in 1.540s — OK**. Esto confirma regresión local, no GitHub Actions ni un cutover físico. El test de conflicto usa un directorio 0755 explícito y hay un caso adicional que conserva el bloqueo para 0775. `RELEASE_AUTHORIZED=NO`.

## CLIENTE v2 — adaptador de archivos durable en laboratorio (19/11/2026)

Implementado `lib/rclone_two_mount_client_file_ops.py`: operaciones de archivos **reales** sobre un par `account1.conf` / `account2.conf` y journal privado con lock `flock`, backup O_EXCL 0600, `fsync`, escritura mediante rename atómico, estado fail-closed ante crash y rollback comprobado. Sólo accede a la cuenta seleccionada. `recovery_pending` mantiene el bloqueo hasta salud confirmada tras rollback; una transacción previa completada tampoco se sobrescribe silenciosamente.

Las operaciones systemd, exclusión de procesos rclone y salud FUSE se reciben como callbacks, **sin adaptador productivo ni conexión a Kodi**. Los tests `test_rclone_two_mount_client_file_ops.py` usan /tmp, dos ficheros ficticios y callbacks; verifican identidad por cuenta, permisos, idempotencia, interrupción y rollback.

**Límite de seguridad:** pasar `enabled=True` a la clase no constituye autorización de despliegue. Falta implementar y validar un adaptador systemd que detenga los dos binds y una raíz FUSE de la cuenta escogida, confirme ausencia de escritor y montajes dependientes, restaure sus dos binds tras iniciar rclone y pruebe medios reales. El writer rclone no respeta automáticamente los locks de Python; se necesita una barrera independiente sobre procesos y generaciones. Falta ensayo de reinicio con corte de energía y recuperación de journal incompleto.

**CI de los nuevos cambios: pendiente de ejecución por el operador.** Estado de release sigue NO.

`CLIENT_V2_DURABLE_FILE_OPS=IMPLEMENTED_GATED`
`CLIENT_V2_SYSTEMD_ADAPTER=NOT_IMPLEMENTED`
`CLIENT_V2_KODIELEC_REAL_TEST=NOT_RUN`
`RELEASE_AUTHORIZED=NO`

## Regresión Ubuntu confirmada por operador — 874/874 (19/11/2026)

El operador ha ejecutado `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'` tras sincronizar `develop` y ha comunicado `Ran 874 tests in 1.394s` seguido de `OK`. Queda validada la suite local, incluidas las pruebas con archivos temporales del adaptador CLIENTE v2. No demuestra integración systemd real, exclusión de escritores rclone físicos ni recuperación tras reinicio. `RELEASE_AUTHORIZED=NO`.

## Integración CLIENTE OAuth v2 con systemd por cuenta — 19/11/2026

**Código en `develop`, NO desplegado ni validado físicamente.** Desde la suite 874/874 anterior se han añadido:

- `lib/rclone_two_mount_client_systemd.py`: adaptador systemd de **una** cuenta: detener dos bind y su FUSE, verificar quiescencia de mountinfo, systemd y procesos rclone con `--config` correspondiente; iniciar primero FUSE y luego los dos bind; health de montaje (incluido rechazo de overmount) y `media_check` obligatorio. No contiene autorización OAuth ni operación automática al importar.
- `lib/rclone_two_mount_client_apply.py`: composición de verificación MQC2/sondeo remoto → transacción de archivos 0600 → callbacks systemd, bloqueo `flock`, Kodi idle, estado v2 `active`, rol `CLIENT`, root y bandera `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED`. No está conectada a `service.py`.
- `lib/rclone_two_mount_client_runtime.py`: devolución del candidato con bytes únicamente mediante `return_candidate=True` **después** de verificación de probe y generaciones. La API de solo estado se conserva.
- `lib/rclone_two_mount_boot_guard.py`: vigilancia de `/storage/.config/masqelec/rclone-v2-client-recovery/account{1,2}`, rechaza journal corrupto, interrumpido, symlink o perteneciente a otra cuenta al arrancar/consultar montajes.
- `lib/constants.py`: `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED = False`, separado de los otros gates; no se activa.
- Nuevas pruebas `test_rclone_two_mount_client_systemd.py`, `test_rclone_two_mount_client_boot_guard.py`, `test_rclone_two_mount_client_apply.py` y nuevas variantes de `test_rclone_two_mount_client_runtime.py`. Los callbacks de systemd son **simulados** y los archivos se escriben solo en directorios temporales.
- En `recover_one` se comprueba Kodi idle y ausencia de recovery pendiente **antes de GET/sondeo OAuth**; se vuelve a comprobar antes de parar la cuenta.

### Puertas abiertas — NO autorizar release

1. **CI local tras estos commits NO CONFIRMADO**. Ejecutar `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'` en Ubuntu con `git pull --ff-only origin develop`; resolver fallos antes de cualquier otra prueba.
2. Falta un proveedor operativo confiable de `AUTH` por cuenta; `get/head` autenticados y callback `probe` en copia temporal 0600 **no están conectados al worker**. Los callbacks simulados no prueban Microsoft OAuth real.
3. Falta provisionar idempotentemente el journal `account1/account2` en 0700 y verificar su recuperación explícita tras apagón. El guard bloquea, pero **no restaura automáticamente** ese journal.
4. Falta ensayo de systemd REAL por cuenta con FUSE y binds bajo rutas y unidades aisladas y prueba de rollback en puntos de fallo. El anterior PASS de laboratorio 2+4 no cubre este circuito OAuth.
5. Falta verificar en MASTER la publicación real cifrada del nuevo `rclone-v2.conf.crypt` bajo CAS y readback; validar CLIENTE actualizado tarde, y equipo legacy que arranca tras el MASTER.
6. Publicación del ZIP y sincronización de repositorio Kodi, responsabilidad del operador. Mantener `main`, `cloud.masqelec` y producción intactos.

`CLIENT_V2_SYSTEMD_ADAPTER=IMPLEMENTED_GATED`
`CLIENT_V2_END_TO_END_CODE=COMPOSED_NOT_CONNECTED`
`CLIENT_V2_REAL_SYSTEMD_RECOVERY=NOT_TESTED`
`CLIENT_V2_REAL_OAUTH_PROBE=NOT_TESTED`
`CLIENT_V2_CRASH_RECOVERY=MANUAL_GUARD_ONLY`
`LATEST_CI_RESULT=NOT_CONFIRMED`
`RELEASE_AUTHORIZED=NO`

## Regresión integrada 902/902 — confirmación operador (19/11/2026)

Tras los commits `3962c60` y `2796965`, se ejecutó en Ubuntu la suite completa `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q`, con resultado `Ran 902 tests in 1.318s` y `OK`. Los mensajes `MASQELEC_EARLY_BOOT=INVALID_MODE`, `MASQELEC_EARLY_BOOT=ROLLED_BACK` y `CLEANUP=COMPLETE` pertenecen a los casos de prueba. **902/902 PASS** verifica los escenarios automatizados, no un montaje real o OAuth Microsoft. 

`CLIENT_V2_UBUNTU_REGRESSION=PASS_902`
`CLIENT_V2_REAL_SYSTEMD_OAUTH_RECOVERY=NOT_VERIFIED`
`RELEASE_AUTHORIZED=NO`

## Nuevo ensayo físico aislado: ciclo de una cuenta (19/11/2026)

Se ha ampliado `tools/rclone_two_mount_systemd_local_lab.py` con `--cycle-account1-isolated --confirm-isolated-only`. Mantiene su entorno local previo: **2 rclone FUSE y 4 bind con backend y archivos locales en /tmp**, seis unidades de nombre aleatorio exclusivamente en `/run/systemd/system`, sin leer configuración rclone real, sin OneDrive y sin modificar Kodi. Tras comprobar el layout inicial:
1. Detiene exclusivamente los dos bind de la cuenta 1 y su raíz FUSE.
2. Verifica que sus tres montajes han desaparecido.
3. Comprueba que la cuenta 2 continúa con sus servicios y sus archivos de prueba accesibles.
4. Reinicia exclusivamente raíz FUSE 1 y sus dos bind; revalida 2 FUSE + 4 bind y lectura de las cuatro muestras.
5. Retira todas las unidades y los montajes temporales en `finally`. Si la limpieza queda incompleta, la prueba falla y conserva evidencias para diagnóstico.

Comando **en dispositivo KodiELEC** desde copia local del script actualizado, con permisos de root:
```bash
python3 service.cloud.masqelec/tools/rclone_two_mount_systemd_local_lab.py --preflight
python3 service.cloud.masqelec/tools/rclone_two_mount_systemd_local_lab.py --cycle-account1-isolated --confirm-isolated-only
```

Resultado esperado: `LAB_RESULT=PASS_REAL_SYSTEMD_ONE_ACCOUNT_RESTART_ISOLATED` y `CLEANUP=COMPLETE`; no declarar PASS si falta cualquiera. Se han añadido tests `test_rclone_two_mount_systemd_account_cycle.py`.

**Límite:** este ensayo verifica stop/start real de las unidades efímeras y aislamiento de cuenta, pero no recupera tokens OAuth, no prueba las rutas reales y no implementa aún restauración automática del journal tras apagón. Por eso `RELEASE_AUTHORIZED=NO`.

## Resultado físico confirmado por operador — ciclo aislado cuenta 1, 19/11/2026

El operador ejecutó en KodiELEC el laboratorio real con `--preflight` y `--cycle-account1-isolated --confirm-isolated-only`. El preflight informó todas las dependencias `YES` y `LAB_RESULT=READY_FOR_ISOLATED_SYSTEMD`. La ejecución informó:

```text
LAB_MODE=RCLONE_2FUSE_4BIND_REAL_SYSTEMD_ISOLATED
ONEDRIVE_ACCESSED=NO
LIVE_RCLONE_CONFIG_READ=NO
KODI_MOUNT_PATHS_CHANGED=NO
LEGACY_SERVICE_START_STOP=NO
LEGACY_UNIT_FILES_CHANGED=NO
SYSTEMD_DAEMON_RELOAD=ISOLATED_RUN_ONLY
SYSTEMD_RUNTIME_UNITS_ONLY=YES
PERMANENT_UNITS_ENABLED=NO
GITHUB_UPLOAD=NO
CLEANUP=COMPLETE
LAB_RESULT=PASS_REAL_SYSTEMD_ONE_ACCOUNT_RESTART_ISOLATED
```

**PASS físico aislado:** las seis unidades efímeras montaron 2 FUSE + 4 bind; se detuvieron/reiniciaron exclusivamente FUSE y dos bind de cuenta 1, con comprobación de lectura de archivos locales de cuenta 2 durante el corte y de ambas tras reiniciar. No prueba tokens OAuth, OneDrive real ni recuperación por apagón. No se modificaron montajes ni servicios de producción. La suite de regresión posterior al script nuevo no se ha comunicado todavía. `RELEASE_AUTHORIZED=NO`.

## Ensayo siguiente (pendiente de ejecución): systemd real + rollback OAuth ficticio

Añadido a `tools/rclone_two_mount_systemd_local_lab.py` el modo `--fake-oauth-rollback-isolated --confirm-isolated-only`, junto con `tests/test_rclone_two_mount_systemd_fake_rollback.py`. Usa únicamente un fichero falso `account1.conf` privado en el `/tmp/masqelec-sd-lab-*` aleatorio del ensayo, backup exclusivo 0600 y journal fsync. Una vez comprobados 2 FUSE + 4 bind temporales:
- detiene dos bind + FUSE de cuenta 1; comprueba ausencia de montajes y lectura de cuenta 2;
- reemplaza atómicamente los bytes de prueba de cuenta 1 y reinicia sus tres unidades;
- inyecta un fallo de salud deliberado, registra `rollback_required`, detiene de nuevo cuenta 1, restaura los bytes anteriores desde backup y reinicia sus tres unidades;
- exige lectura correcta de las cuatro muestras y credenciales restauradas; marca `rolled_back_verified` solo después;
- desmonta y elimina todo el laboratorio temporal; cualquier limpieza incompleta exige revisión manual.

**Esto NO es** una recuperación OAuth de Microsoft, ni una prueba de apagón, ni una prueba del flujo productivo. No accede a `/storage/.config/rclone`, no publica a GitHub ni toca servicios legacy. La suite anterior reportada por operador fue 902/902 PASS; los tests de este nuevo cambio están PENDIENTES de ejecutar.

Comandos: `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q` en Ubuntu y en KodiELEC `python3 /tmp/rclone_two_mount_systemd_local_lab.py --fake-oauth-rollback-isolated --confirm-isolated-only` tras bajar la última versión del script en `develop`.

Marcadores exigidos: `CLEANUP=COMPLETE` y `LAB_RESULT=PASS_REAL_SYSTEMD_FAKE_OAUTH_ROLLBACK_ISOLATED`. `RELEASE_AUTHORIZED=NO`.

## Resultado confirmado por operador: 911/911 + rollback físico aislado PASS

El operador reporta en Ubuntu `Ran 911 tests in 1.333s` / `OK` tras incorporar las pruebas del rollback ficticio. Los marcadores `MASQELEC_EARLY_BOOT=INVALID_MODE`, `MASQELEC_EARLY_BOOT=ROLLED_BACK` y `LAB_RESULT=BLOCKED_INVALID_MODE` corresponden a ensayos negativos, no a fallos de la suite.

En KodiELEC, el laboratorio de `--fake-oauth-rollback-isolated --confirm-isolated-only` ha devuelto:
```text
LAB_MODE=RCLONE_2FUSE_4BIND_REAL_SYSTEMD_ISOLATED
ONEDRIVE_ACCESSED=NO
LIVE_RCLONE_CONFIG_READ=NO
KODI_MOUNT_PATHS_CHANGED=NO
LEGACY_SERVICE_START_STOP=NO
LEGACY_UNIT_FILES_CHANGED=NO
SYSTEMD_DAEMON_RELOAD=ISOLATED_RUN_ONLY
SYSTEMD_RUNTIME_UNITS_ONLY=YES
PERMANENT_UNITS_ENABLED=NO
GITHUB_UPLOAD=NO
CLEANUP=COMPLETE
LAB_RESULT=PASS_REAL_SYSTEMD_FAKE_OAUTH_ROLLBACK_ISOLATED
```

**Gates superados**: regresión automatizada 911/911 en Ubuntu y ensayo físico aislado de rollback de bytes ficticios con systemd en KodiELEC, preservando los montajes reales.

**No cubre**: sonda OAuth Microsoft real; validación real del paquete MQC2 MASTER/CLIENT; crash/reinicio durante transición; conexión del worker a `recover_one` y garantía de mismo candidato probado y aplicado. `RELEASE_AUTHORIZED=NO`, gates de producción `False`.

## Integración CLIENTE v2 funcional con puertas cerradas — revisión final de código (19/11/2026)

Desde los 911 tests confirmados y el ensayo KodiELEC ficticio PASS, se incorporaron los siguientes módulos y enlaces en `develop`:

1. `lib/rclone_two_mount_client_worker.py`: activo solo si `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED`, rama `develop`, rol `CLIENT`, layout `active` y Kodi idle. Consulta por hora, detecta `auth` **solo mediante sonda rclone en config temporal privada**, nunca confunde errores de red o límites de tasa con AUTH. Recupera únicamente la cuenta seleccionada.
2. `lib/rclone_two_mount_client_runtime.py`: la sonda de candidato puede devolver `("ok", bytes_renovados)`; compara opciones no-token con el candidato y transporta **el token realmente probado**, manteniendo comparación de fuentes locales y HEAD remoto posteriores. No acepta renovación sin éxito inequívoco.
3. `lib/rclone_two_mount_client_apply.py`: integra autenticación/sonda a `AccountFileOps` + `AccountSystemd` mediante `recover_one`, comprobación Kodi idle antes y después del sondeo, lock + backup 0600 + journal y rollback por cuenta. Inicializa journal de forma limitada bajo un directorio privado ya confiable, solo con gates activos.
4. `lib/rclone_token_sync.py`: llama al worker CLIENTE v2 en el tick existente de un layout activo y solo si la nueva bandera se habilita. El CLIENTE no publica MQC2 ni vuelve a la URL legacy. El MASTER v2 conserva su ruta previa.
5. `lib/rclone_two_mount_client_crash_recovery.py` y `lib/rclone_two_mount_client_early_boot.py`: reinicio con journal pendiente → detener solo la cuenta afectada, verificar ausencia de montajes/escritores, restaurar backup 0600 mediante rename+fsync, reiniciar solo la cuenta afectada, comprobar medio y marcar `rolled_back` únicamente tras salud confirmada. Journal corrupto o recuperación incompleta permanece bloqueada.
6. `tools/rclone_two_mount_early_boot_run.py`: runner opcional bifurcado según bandera y rol. `lib/rclone_two_mount_boot_install.py` **corregido** para pasar el argumento exigido `--recover` en `ExecStart` (antes faltaba, y habría impedido la recuperación).
7. Pruebas nuevas `test_rclone_two_mount_client_crash_recovery.py`, `test_rclone_two_mount_client_early_boot.py`, `test_rclone_two_mount_client_worker.py` y regresiones adicionales para token renovado, identidad, permisos del journal y el nuevo `ExecStart`.

**Todas las banderas permanecen `False` por defecto.** Ni este desarrollo ni los tests nuevos han tocado remotos, OneDrive o montajes de producción.

### Validación pendiente antes de considerar release

- **Suite Python tras los últimos commits: NO EJECUTADA/NO CONFIRMADA.** Última confirmación anterior: 911/911 OK. El siguiente comando en Ubuntu es `git pull --ff-only origin develop && python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q`. Resolver cualquier fallo sin tocar producción.
- **Ensayo físico de fallo real de proceso/reinicio** del journal CLIENTE y del orden early-boot con unidades aisladas y validación de que el segundo FUSE/los otros dos bind no sufren interrupción: PENDIENTE.
- **OAuth Microsoft auténtico**: sonda de cuenta con estado AUTH demostrado y candidato v2 con refresh válido, sin exponer tokens; PENDIENTE.
- **MQC2 v2 MASTER**: publicación real CAS/readback en `masQelec/cloud.masqelec/develop` y compatibilidad de CLIENTES desfasados: PENDIENTE, sin writes a remoto autorizados.
- **Release de addon Kodi** y activación de flags: NO AUTORIZADAS. El usuario se ocupa de publicar el ZIP una vez superados los gates.

`CLIENT_V2_WORKER_CODE=CONNECTED_GATED_OFF`
`CLIENT_V2_RESTART_RECOVERY_CODE=CONNECTED_GATED_OFF`
`EARLY_BOOT_RECOVER_ARG=FIXED`
`LATEST_OPERATOR_TESTS=911_PASS_PRIOR_COMMITS`
`NEW_TESTS=AWAITING_OPERATOR`
`REAL_OAUTH_END_TO_END=NOT_VERIFIED`
`REAL_REBOOT_RECOVERY=NOT_VERIFIED`
`MASTER_V2_PUBLISH=NOT_VERIFIED`
`RELEASE_AUTHORIZED=NO`

## Corrección de regresión tras integración CLIENTE (19/11/2026)

El operador ejecutó la suite y obtuvo `Ran 932 tests in 1.349s` / `FAILED (errors=3)`. Las causas observadas: dos pruebas de journal invocaban `self.root` sin inicializar en `setUp`; el nuevo worker importaba `rclone_token_sync` en el nivel módulo, arrastrando `log_utils`/Kodi `xbmc` no disponible en Ubuntu. Correcciones publicadas en `develop`: `self.root=root`, carga tardía de `rclone_token_sync` mediante `_token_probe` sólo en la sonda y tests mockeando esa función aislada. Commits `77b4a6e5`, `402e811b`, `362a19f1`.

**La suite corregida aún no se ha ejecutado por el operador.** No declarar PASS ni habilitar producción hasta confirmar ejecución y gates físicos/OAuth. `RELEASE_AUTHORIZED=NO`.
