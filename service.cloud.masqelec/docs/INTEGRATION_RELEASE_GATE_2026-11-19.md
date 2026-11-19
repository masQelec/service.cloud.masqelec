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

## Regresión 938/938 PASS — confirmación operador (19/11/2026)

El operador ejecutó la suite completa tras corregir la inicialización de `self.root` y la importación diferida de `rclone_token_sync` en el worker CLIENTE. Resultado: `Ran 938 tests in 1.430s` y `OK`. Las salidas `MASQELEC_EARLY_BOOT=INVALID_MODE`, `MASQELEC_EARLY_BOOT=ROLLED_BACK`, `LAB_RESULT=BLOCKED_INVALID_MODE` y `CLEANUP=COMPLETE` pertenecen a los ensayos automatizados. La suite confirma las regresiones Python actuales, pero NO demuestra reinicio/corte real, OAuth Microsoft ni publicación MASTER MQC2. `RELEASE_AUTHORIZED=NO`.

## Cierre siguiente de integridad CLIENTE v2 — persistencia entre procesos y recuperación repetida (19/11/2026)

Desde la regresión confirmada por el operador `938/938 OK` se incorporó:

- `tests/test_rclone_two_mount_client_restart_process.py`: prueba durable **entre dos procesos Python independientes**: el primero efectúa snapshot 0600/0700, instala un token ficticio y finaliza sin commit; el segundo carga el journal real desde disco con `rclone_two_mount_client_crash_recovery.restore_interrupted`, restaura los bytes anteriores y comprueba la segunda cuenta intacta. No modifica Kodi, systemd, OneDrive o credenciales reales. No es un apagón/reboot físico.
- `lib/rclone_two_mount_client_file_ops.py::retire_finalized`: corregido bloqueo funcional previo que rechazaba cualquier renovación OAuth posterior al primer journal completado. Solo bajo lock, tras verificar bytes/generación actual, se retira un journal explícitamente `committed` o `rolled_back`, verificando tipo, identidad y permisos 0600 de su backup, sin seguir symlinks ni borrar estados parciales; `fsync` de directorio entre borrados. Con nuevo incidente AUTH se crea snapshot nuevo y solo se modifica la cuenta objetivo.
- Tests adicionales: segunda recuperación independiente por cuenta, rechazo de candidato obsoleto y de journal incompleto o backup enlazado.

**NUEVA REGRESIÓN pendiente de ejecución por operador**: `git pull --ff-only origin develop && python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q`. Última ejecución conocida: 938/938 OK **anterior** a estos commits.

**No cerrar release aún**: falta validar el apagón/reboot físico de KodiELEC y recuperación productiva de journal bajo systemd, validar OAuth Microsoft auténtico y publicar/probar MQC2 MASTER con CAS/readback. Los ensayos ficticios no acreditan esos hechos. Todas las banderas de release siguen desactivadas. `RELEASE_AUTHORIZED=NO`.

## Confirmación del operador — regresión 941/941 PASS (19/11/2026)

El operador ejecutó `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q` tras los cambios de persistencia entre procesos y retiro controlado de journals finalizados: `Ran 941 tests in 1.395s` / `OK`. Los marcadores `MASQELEC_EARLY_BOOT=INVALID_MODE`, `MASQELEC_EARLY_BOOT=ROLLED_BACK`, `LAB_RESULT=BLOCKED_INVALID_MODE` y `CLEANUP=COMPLETE` proceden de tests. Se confirma la regresión automatizada, **no** el reinicio físico ni OAuth de Microsoft. `RELEASE_AUTHORIZED=NO`.

## Laboratorio de persistencia tras reinicio REAL — dos fases, pendientes de operador

En `develop` se añade `tools/rclone_two_mount_reboot_journal_lab.py`, autocontenido para KodiELEC y ejecutable desde `/tmp`. No importa los módulos del addon instalado. El script escribe **únicamente** en `/storage/.config/masqelec-v2-reboot-journal-lab`, directorio privado 0700 exclusivo; genera cuenta 1 ficticia, respaldo y cuenta 2 ficticia (0600), deja journal fase `install_requested` con fsync y almacena `/proc/sys/kernel/random/boot_id`. No toca configuraciones OAuth ni montajes reales, unidades systemd o biblioteca Kodi. No lanza reboot.

**Antes del reinicio**: descargar el script de `raw.githubusercontent.com/masQelec/service.cloud.masqelec/develop/service.cloud.masqelec/tools/rclone_two_mount_reboot_journal_lab.py` en `/tmp/masqelec_reboot_lab.py` y ejecutar `python3 /tmp/masqelec_reboot_lab.py --prepare --confirm-isolated-only`. Requiere `REBOOT_LAB_RESULT=PREPARED_REBOOT_REQUIRED`. Si hay un directorio existente o una condición insegura, bloqueará sin reemplazarlo.

**Reiniciar KodiELEC manualmente** sin ejecutar ningún comando del script durante el proceso de apagado. Tras iniciar, descargar otra vez el script si `/tmp` se ha limpiado y ejecutar `python3 /tmp/masqelec_reboot_lab.py --verify-after-reboot --confirm-isolated-only`. Requiere cambio de boot_id real, journal idéntico, credenciales ficticias intactas y cuenta 2 intacta; restaura cuenta 1 original, sincroniza y elimina solo los archivos exactos del laboratorio, retornando `REBOOT_LAB_RESULT=PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK`.

Se incorpora `tests/test_rclone_two_mount_reboot_journal_lab.py` (6 escenarios) para fail-closed, reinicio requerido, persistencia y rechazo de contenido ajeno/corrupto. **Regresión y ensayo físico pendientes de resultados**. Última suite confirmada previamente: 941/941 OK.

**Límite fundamental**: prueba persistencia del journal y restauración de bytes ficticios tras boot_id diferente, NO valida orden de unidad systemd antes de Kodi, recuperación automáticamente ejecutada por el addon, continuidad de FUSE real ni OAuth Microsoft. Por tanto `RELEASE_AUTHORIZED=NO`.

## Resultado físico confirmado: persistencia/rollback tras reboot real en CoreELEC

El operador ejecutó en el equipo CoreELEC 21.2.5-Omega_devel (Amlogic-ng.arm) la fase `--prepare --confirm-isolated-only` del laboratorio `tools/rclone_two_mount_reboot_journal_lab.py`, obteniendo `REBOOT_LAB_RESULT=PREPARED_REBOOT_REQUIRED`. A continuación ejecutó `reboot`, se perdió la sesión SSH por reinicio y se reconectó tras arrancar. La verificación manual `--verify-after-reboot --confirm-isolated-only` devolvió `REBOOT_LAB_RESULT=PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK`.

Marcadores declarados por el laboratorio: `REAL_OAUTH_ACCESSED=NO`, `SYSTEMD_UNITS_CHANGED=NO`, `KODI_MOUNTS_CHANGED=NO`, `REBOOT_TRIGGERED=NO`. El programa verifica cambio del `boot_id`, integridad exacta del journal y bytes ficticios, restaura la cuenta 1, comprueba que la cuenta 2 ficticia no cambia y limpia exclusivamente su ruta persistente privada.

**GATE_REAL_REBOOT_FAKE_JOURNAL_PERSISTENCE=PASS**. Este resultado **NO prueba** la ejecución automática de la recuperación previa a Kodi, systemd productivo ni OAuth/MQC2 real. La última suite Python confirmada por operador fue 941/941 PASS antes de incorporar los seis tests de este laboratorio; sigue pendiente la regresión de los últimos commits. `RELEASE_AUTHORIZED=NO`.

## Gate agrupado de cierre, solo lectura (19/11/2026)

Disponible `tools/rclone_two_mount_final_gate.py`, con dos modos independientes y sin escritura de configuración, systemd, OneDrive ni Kodi:

**Ubuntu:** `python3 service.cloud.masqelec/tools/rclone_two_mount_final_gate.py --ubuntu-regression`. Ejecuta toda la suite Python y exige retorno `FINAL_GATE=PASS_REGRESSION`.

**KodiELEC:** descargar el fichero RAW a `/tmp/masqelec_final_gate.py` y ejecutar `python3 /tmp/masqelec_final_gate.py --coreelec-readonly`. Inspecciona `systemctl show` de `kodi.service` y `masqelec-v2-recovery.service`; verifica `Wants`, `After`, `Before` y que el `ExecStart` real incluya `--recover`. Si todavía no existe la unidad o no está ordenada, devuelve `FINAL_GATE=BLOCKED_AUTOMATIC_BOOT_ORDER_NOT_VERIFIED`, resultado correcto y seguro para un despliegue aún no realizado. **No instala ni activa unidades**.

**Limitación:** incluso `PASS_INSTALLED_ORDERING_READONLY` demostraría la topología de dependencias, no que un journal real se haya recuperado automáticamente en pre-Kodi. La puesta en marcha del recuperador CLIENTE y OAuth/MQC2 reales continúan pendientes. `PRODUCTION_RELEASE_AUTHORIZED=NO`.

## Auditoría CoreELEC solo lectura — unidad pre-Kodi ausente (operador)

Ejecutado `tools/rclone_two_mount_final_gate.py --coreelec-readonly`. Resultado:
```text
CORE_ELEC_HOST_ROOT=YES
KODI_SYSTEMD_LOADED=YES
EARLY_BOOT_UNIT_LOADED=NO
KODI_WANTS_RECOVERY=NO
KODI_AFTER_RECOVERY=NO
RECOVERY_BEFORE_KODI=NO
RECOVERY_EXEC_RECOVER_ARG=NO
OAUTH_OR_CONFIG_READ=NO
SYSTEMD_MODIFICATIONS=NO
KODI_MOUNTS_MODIFIED=NO
FINAL_GATE=BLOCKED_AUTOMATIC_BOOT_ORDER_NOT_VERIFIED
PRODUCTION_RELEASE_AUTHORIZED=NO
```
Diagnóstico preciso: la unidad `masqelec-v2-recovery.service` no está instalada en CoreELEC; por tanto tampoco hay dependencia `Wants/After` ni un `ExecStart` verificable. **Esto no demuestra fallo del código de recuperación** y tampoco prueba la ejecución automática. No instalarla sobre `kodi.service` productivo sin autorización de release y ensayo aislado. Falta comunicar resultado del modo `--ubuntu-regression`.

## Laboratorio en MASTER ejerciendo solo la lógica CLIENT OAuth v2

A petición del operador, `develop` incorpora la bandera específica `RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER=False` en `lib/constants.py` y la decisión pura `lib/rclone_two_mount_client_role.py`. Cuando la bandera se activa **únicamente en la copia local del addon del MASTER de desarrollo**, el worker OAuth v2, su `recover_one` y el recuperador CLIENT de arranque temprano aceptan ese equipo como sujeto de prueba CLIENT; **no cambia** `device_utils.get_device_role()`, el catálogo o el comportamiento normal de otros componentes. Se inhibe la publicación MASTER v2 durante el ensayo para evitar funciones contrapuestas en el mismo tick.

El mero cambio de esa bandera NO habilita acciones: `RCLONE_TOKEN_SYNC_ENABLED`, `RCLONE_TWO_MOUNT_FEATURE_ALLOWED`, `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED`, estado local `active`, idle de Kodi, salud de medios y el resto de guardas mantienen sus requisitos. Los nuevos tests `test_rclone_two_mount_client_role.py` verifican aislamiento y ausencia de autorización implícita.

**No activar todas las banderas ni forzar marcadores solo para satisfacer la prueba.** Primero confirmar regresión y verificar/instalar la unidad real de arranque en el equipo de desarrollo con preflight/rollback. Un MASTER en estado legacy no puede ejercer honestamente la recuperación OAuth CLIENT v2 de un sistema active sin completar una migración controlada. La prueba de tokens OneDrive reales y publicación MQC2 sigue pendiente. `RELEASE_AUTHORIZED=NO`.

## Operación directa sobre el MASTER CoreELEC de desarrollo: unidad REAL de arranque

El operador ha confirmado que el equipo MASTER es de desarrollo y puede ejercer **solo la función OAuth CLIENTE v2** sin alterar su rol global. Tras `950/950` pruebas Python PASS confirmadas por el operador (antes de este cambio), se ha añadido `tools/rclone_two_mount_dev_boot_install.py` y sus tests en `test_rclone_two_mount_dev_boot_install.py`.

**Alcance**: instala mediante `lib/rclone_two_mount_boot_install.ensure_installed` los dos archivos **reales** `/storage/.config/system.d/masqelec-v2-recovery.service` y `/storage/.config/system.d/kodi.service.d/50-masqelec-v2-recovery.conf`. Solo operador explícito `--install-real-boot-unit --confirm-dev-device`. Verifica `Wants/After` de Kodi, que `ExecStart` usa `--recover`, permisos y contenido exacto, y que el runner realmente reside en `/storage/.kodi/addons/service.cloud.masqelec/tools`. No gestiona otros servicios ni toca config/token OAuth. Un comando `--remove-real-boot-unit --confirm-dev-device` retira solo esos archivos si los bytes siguen idénticos. No elimina el directorio `kodi.service.d` ni ficheros ajenos.

**Puertas de seguridad**: requiere root, instalación desde árbol REAL del addon, carpeta systemd confiable, flag `RCLONE_TWO_MOUNT_FEATURE_ALLOWED=False`, `RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED=False`, `RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED=False`, `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED=False`, `RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED=False`. No activa recuperación OAuth. Si alguna bandera ya está en True, aborta. Por tanto la primera ejecución real de la unidad antes de Kodi debe informar `MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED` o similar, y NO realizar rollback/montajes.

**Secuencia controlada:** primero actualizar el addon **del dispositivo de desarrollo** con los cambios de `develop` de forma controlada; no basta descargar este ejecutable a `/tmp` porque exige su ubicación real. Hacer respaldo de la versión instalada antes de reemplazarla. Después `python3 /storage/.kodi/addons/service.cloud.masqelec/tools/rclone_two_mount_dev_boot_install.py --preflight` → `BOOT_DEV_RESULT=READY_DISABLED_ONLY`; luego `--install-real-boot-unit --confirm-dev-device` → `BOOT_DEV_RESULT=READY_REAL_BOOT_ORDER_INSTALLED`. Ejecutar auditoría `--coreelec-readonly` y verificar `FINAL_GATE=PASS_INSTALLED_ORDERING_READONLY`. Solo entonces reiniciar voluntariamente, comprobar `journalctl -b -u masqelec-v2-recovery.service --no-pager` y estado de Kodi. Si hay problema o se termina el ensayo: `--remove-real-boot-unit --confirm-dev-device`; no tocar los demás servicios.

**Estado de los tests nuevos:** sin ejecutar por el operador todavía. `RELEASE_AUTHORIZED=NO`. Validar unidad instalada **no** es lo mismo que demostrar recuperación automática de un journal OAuth real; ese gate sigue pendiente junto con prueba Microsoft OneDrive/MQC2 real.

## Regresión instalador real (957 tests, 1 fallo) — corrección fixture de umask

El operador ejecutó `Ran 957 tests in 1.417s` con un fallo: `test_remove_only_exact_owned_files` esperaba `REMOVED_OWN_UNIT_AND_DROPIN` pero recibió `BLOCKED_REMOVE_FAILED`. La prueba creaba `kodi.service.d` con `mkdir()` sin fijar modo, haciendo que una umask permisiva dejara el directorio con bit de escritura al grupo; `atomic.remove_if_identical` rechaza por diseño directorios con `0o022`. La fixture se ha actualizado con `chmod(0o755)`, también en el test de configuración ajena. Se añadió una prueba específica que asegura que con `0o775` la retirada queda bloqueada y conserva los archivos. **No se ha relajado ninguna validación de seguridad en producción.**

Nueva ejecución de la regresión pendiente. Hasta entonces no instalar la unidad real ni ejecutar reboot del MASTER de desarrollo. `RELEASE_AUTHORIZED=NO`.

## Confirmación operador: regresión dev boot installer 958/958 PASS

Tras corregir fixtures umask de permisos `kodi.service.d` y añadir test de rechazo 0775, el operador ejecutó la suite completa: `Ran 958 tests in 1.430s` / `OK`. `TEST_GATE=PASS_958`. **Aún no hay evidencia de instalación de unidad pre-Kodi** en CoreELEC. Proceder solamente tras preflight de addon realmente actualizado y con flags de migración/recuperación desactivados. El MASTER de desarrollo no implica habilitación de OAuth. `RELEASE_AUTHORIZED=NO`.

## Instalación directa de la unidad pre-Kodi en CoreELEC de desarrollo — PASS

El operador inspeccionó `/storage/.config/system.d`: directorio `root:root`, inicialmente `0775`; las rutas de unidad y drop-in no existían. Se aplicó `chmod 755 /storage/.config/system.d` y el preflight del addon instalado devolvió `BOOT_DEV_RESULT=READY_DISABLED_ONLY`. La ejecución autorizada del instalador real `rclone_two_mount_dev_boot_install.py --install-real-boot-unit --confirm-dev-device` devolvió `BOOT_DEV_RESULT=READY_REAL_BOOT_ORDER_INSTALLED`. El instalador usa `boot_install.ensure_installed` con `systemctl daemon-reload` y verificación `kodi.service Wants/After`. Marcadores reportados: `OAUTH_OR_CREDENTIALS_CHANGED=NO`, `RCLONE_MOUNT_UNITS_CHANGED=NO`, `KODI_LIBRARY_CHANGED=NO`.

**GATE_DEV_BOOT_INSTALL=PASS**. Pendiente comprobación independiente `--coreelec-readonly`, reinicio real y observación `journalctl -b -u masqelec-v2-recovery.service`. La instalación no demuestra recuperación automática de una transacción interrumpida. Flags de OAuth/migración continúan desactivados. `RELEASE_AUTHORIZED=NO`.

## Gate ejecutado: unidad real de recuperación lanzada en boot CoreELEC

Evidencia aportada por el operador: `journalctl -b -u masqelec-v2-recovery.service` muestra `Starting masqelec-v2-recovery.service`, `MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED`, `Deactivated successfully` y `Finished masqelec-v2-recovery.service`. `systemctl show` informó `Result=success`, `LoadState=loaded`, `ActiveState=inactive` (esperado para Type=oneshot sin RemainAfterExit) y `Before=kodi.service shutdown.target`. `systemctl status kodi.service` mostró drop-in `50-masqelec-v2-recovery.conf` cargado. Por tanto `DEV_REAL_BOOT_RUNNER_EXECUTED=PASS`, `DEV_UNAUTHORIZED_NO_RECOVERY=PASS`, `DEV_UNIT_BEFORE_DEPENDENCY_CONFIGURED=PASS`; NO declarar aún gate de restauración automática de journal real ni OAuth. La captura parcial de `systemd-analyze critical-chain` no muestra la unidad, por lo que conviene confirmar las marcas de tiempo relativas con `journalctl -b -o short-monotonic -u kodi.service -u masqelec-v2-recovery.service`.

La salida de journal presenta fecha `Feb 27` sin año mientras la conversación es de noviembre de 2026: revisar reloj del dispositivo antes de usar fechas de wall-clock como evidencia; las marcas monotónicas del mismo arranque son preferibles. `RELEASE_AUTHORIZED=NO`.

## Gate de orden REAL de arranque pre-Kodi — PASS (evidencia monotónica)

El operador comprobó en CoreELEC mediante `journalctl -b -o short-monotonic -u masqelec-v2-recovery.service -u kodi.service --no-pager`: inicio de recuperación `[6.135086]`, `MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED` `[8.644896]`, finalización de recuperador `[8.735075]`, inicio `kodi.service` `[15.949814]` y arranque Kodi `[16.036970]`. Separación de **7.214739 s** desde `Finished masqelec-v2-recovery.service` hasta `Starting kodi.service`. `GATE_REAL_SYSTEMD_PRE_KODI_ORDER=PASS` y `GATE_DENIED_RECOVERY_NO_SIDE_EFFECT=PASS` conforme a la ruta autorizada, que permanece deshabilitada. Marcas de reloj monotónico evitaban discrepancias de wall clock del dispositivo.

**No demostrar más de lo medido:** no existe todavía evidencia de restauración OAuth automática de un journal real ni de operación MQC2 MASTER/CLIENTE. `RELEASE_AUTHORIZED=NO`.

## Ensayo REAL de ejecución automática del journal ficticio ANTES de Kodi — preparado (19/11/2026)

En `develop`, la unidad **real ya instalada** `masqelec-v2-recovery.service` sigue ejecutando `tools/rclone_two_mount_early_boot_run.py --recover`. El runner incorpora el hook privado `_dev_fake_boot_lab()`, con nueva bandera predeterminada `RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED=False` en `lib/constants.py`. **Solo cuando esta bandera se habilita localmente en el MASTER de desarrollo y existe el journal exacto** de `rclone_two_mount_reboot_journal_lab.py`, el proceso unitario llama a `lab.verify()` antes de Kodi. Comprueba los bytes ficticios, permisos, mountinfo, boot_id cambiado y Kodi ausente; realiza rollback ficticio y limpieza exacta. Luego continúa por la ruta habitual, que permanece `MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED`. La salida esperada de la unidad incluye `MASQELEC_DEV_FAKE_BOOT_LAB=PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK`.

El hook **rechaza** si las banderas `RCLONE_TWO_MOUNT_FEATURE_ALLOWED`, `RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED`, `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED` o `RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED` están habilitadas, o si Kodi está arrancado. No llama al sistema de remotos reales, no cambia la función MASTER ni toca `/storage/.config/rclone` ni `/storage/.mnt`. Se han añadido tests de ejecución opt-in, rechazo de Kodi activo y encadenamiento real API lab↔runner con cambio de boot_id simulado.

### Procedimiento para el operador en el único equipo MASTER de desarrollo

1. Ejecutar **regresión completa** en Ubuntu tras `git pull --ff-only origin develop`. **Pendiente**; no asumir PASS.
2. Actualizar en CoreELEC el addon instalado con esta versión de `develop`; no basta actualizar la copia de Ubuntu. Mantener las banderas reales de migración/OAuth desactivadas.
3. Solo en la copia local instalada del MASTER de desarrollo, establecer `RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED=True` (nunca commit a GitHub). Confirmar que la unidad sigue apuntando al runner real del addon instalado.
4. Ejecutar `python3 /storage/.kodi/addons/service.cloud.masqelec/tools/rclone_two_mount_reboot_journal_lab.py --prepare --confirm-isolated-only` y exigir `REBOOT_LAB_RESULT=PREPARED_REBOOT_REQUIRED`.
5. Reiniciar manualmente. Tras la reconexión, `journalctl -b -o short-monotonic -u masqelec-v2-recovery.service -u kodi.service --no-pager`. Se exige el marcador `MASQELEC_DEV_FAKE_BOOT_LAB=PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK` **antes** de `Starting kodi.service`, `MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED` y Kodi arrancado. Comprobar `test ! -e /storage/.config/masqelec-v2-reboot-journal-lab`.
6. Devolver `RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED=False` en el addon local de desarrollo; reiniciar o iniciar nueva instancia del runner para verificar que el hook está inactivo. No borrar manualmente un journal que haya fallado; conservar evidencia.

**Este gate verifica la recuperación automática del journal ficticio por el servicio REAL pre-Kodi**, no un OAuth real, no la restauración de cuentas OneDrive productivas ni MQC2 de GitHub. No habilitar release/first-run/mount migration. `RELEASE_AUTHORIZED=NO`.

## GATE: recuperación automática de journal ficticio mediante systemd REAL antes de Kodi — PASS

Evidencia observada por el operador en CoreELEC tras reinicio, `journalctl -b -o short-monotonic -u masqelec-v2-recovery.service -u kodi.service --no-pager`:

```text
[6.065227] Starting masqelec-v2-recovery.service...
[8.624102] MASQELEC_DEV_FAKE_BOOT_LAB=PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK
[8.624102] MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED
[8.722882] Finished masqelec-v2-recovery.service.
[15.994755] Starting kodi.service...
[16.077740] Started kodi.service.
JOURNAL_LAB_CLEAN=YES
```

La unidad real restauró automáticamente los bytes ficticios del primer archivo tras detectar nuevo `boot_id`, comprobó la segunda cuenta intacta y limpió exclusivamente el directorio privado del ensayo. Kodi arrancó normalmente, **7.271873 s** después de terminar el recuperador. El código REAL continúa bloqueado por `BLOCKED_NOT_AUTHORIZED`, como se pretendía. `GATE_DEV_REAL_SYSTEMD_AUTOMATIC_FAKE_JOURNAL=PASS`.

**Acción necesaria tras ensayo:** devolver `RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED=False` en el addon instalado del MASTER de desarrollo; comprobar que no quedan journal de laboratorio ni activación de esa bandera. No activar automáticamente OAuth real ni migrar otros clientes. Siguen pendientes validación OAuth OneDrive real, publicación/lectura MQC2 MASTER-CLIENT, recuperación auténtica y autorización de release. `RELEASE_AUTHORIZED=NO`.

## Cierre confirmado del laboratorio en dispositivo (operador)

El operador confirmó `LAB_CLEAN=YES` (no existe el directorio de journal ficticio) y `RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED=False` en el addon instalado. `GATE_DEV_FAKE_BOOT_LAB_CLOSED=PASS`. El cierre no autoriza activar OAuth de producción, publicar MQC2, migrar servicios ni desplegar el addon. `RELEASE_AUTHORIZED=NO`.

## Gate agrupado de preparación OAuth REAL — implementación read-only, sin activación

Se añadió `tools/rclone_two_mount_real_oauth_grouped_preflight.py --read-only` para concentrar en una ejecución las comprobaciones previas a una prueba OAuth real usando el dispositivo MASTER como CLIENTE OAuth de laboratorio. El comando inspecciona sin imprimir bytes secretos: rol MASTER, rama `develop`, banderas de release/aplicación desactivadas, laboratorio previo desactivado y limpio, estado local `legacy/prepared/active/unsafe`, permisos y existencia de `rclone.conf` y ambos `accountN.conf`, journal de recuperación pendiente, seis unidades systemd, presencia de dos FUSE y cuatro bind en `/proc/self/mountinfo` y ruta fija GitHub MQC2 v2. **No ejecuta rclone, red, OAuth, recuperación, actualización de addon, systemctl reload/start/stop ni migración.**

La salida `PILOT_GATE=BLOCKED_V2_LAYOUT_NOT_VERIFIED` es **esperable** si el equipo sigue en cuatro FUSE legacy. No falsificar marcador `active` para pasar el preflight. `PILOT_GATE=READONLY_ACTIVE_LAYOUT_PRESENT_NEEDS_OAUTH_GATES` significa únicamente que aparecen componentes de disposición activos; no certifica identidad MQC2, salud de contenido ni tokens. Estas verificaciones requieren gates separados y posterior ensayo de OAuth auténtico.

Pruebas nuevas `tests/test_rclone_two_mount_real_oauth_grouped_preflight.py`: modo inválido, no root, rechazo de flags, laboratorio no desactivado, no MASTER, configuración local insegura, ausencia bind y auditoría positiva simulada. **Pruebas no ejecutadas en el host operador todavía**.

Procedimiento del operador (después de `git pull --ff-only origin develop`, regresión total y actualizar addon de CoreELEC): `python3 /storage/.kodi/addons/service.cloud.masqelec/tools/rclone_two_mount_real_oauth_grouped_preflight.py --read-only`. Enviar únicamente las líneas de estado, nunca `rclone.conf`, tokens, MQC2 cifrado, `authorized_keys` ni credenciales GitHub. Los flags reales continúan deshabilitados. `RELEASE_AUTHORIZED=NO`.

## Preflight OAuth agrupado — bloqueo standalone role solucionado (pendiente regresión física)

El operador informó `PILOT_GATE=BLOCKED_ROLE_UNAVAILABLE` al ejecutar el nuevo script por SSH en CoreELEC. Diagnóstico de código: el auditor importaba `lib.device_utils` que importa `xbmcvfs` a nivel módulo; este módulo Kodi no está disponible necesariamente en el `/usr/bin/python3` del shell independiente. **No demuestra fallo de identidad MASTER**.

Corrección en `tools/rclone_two_mount_real_oauth_grouped_preflight.py`: detección MASTER independiente de Kodi, exclusivamente de lectura, que extrae mediante AST los dos literales de identidad originales de `lib/device_utils.py`, lee la MAC eth0 de sysfs, comprueba su inclusión en la lista permitida y exige también el `n=` del fichero ZeroTier escogido con la misma prioridad de directorios. Ante fuente inaccesible/ilegible devuelve bloqueo o rol desconocido, nunca eleva a MASTER. No altera `device_utils.get_device_role()`, servicio Kodi, configuración ZeroTier ni banderas OAuth. Se incorporaron pruebas nuevas de identidad positiva, negativa y fail-closed.

**Acción del operador:** `git pull --ff-only origin develop`, ejecutar regresión `unittest discover`, actualizar addon instalado en CoreELEC, repetir `tools/rclone_two_mount_real_oauth_grouped_preflight.py --read-only`. El modo legacy activo debe seguir dando `BLOCKED_V2_LAYOUT_NOT_VERIFIED`; es resultado diagnóstico y no autoriza falsificar marcador. `RELEASE_AUTHORIZED=NO`.

## Auditoría física agrupada MASTER — legado confirmado, NO activar OAuth v2

Evidencia del equipo de desarrollo enviada por el operador:
```text
DEVICE_ROLE=MASTER
DEV_CLIENT_OVERRIDE=OFF
MODE=legacy
LOCAL_CONFIG=PRIVATE
ACCOUNT1_CONFIG=MISSING_OR_UNSAFE
ACCOUNT2_CONFIG=MISSING_OR_UNSAFE
CLIENT_JOURNAL_PENDING=NO
EARLY_BOOT_UNIT=loaded
UNIT_1..6=inactive
FUSE_1..2=NOT_MOUNTED
BIND_1..4=MOUNTED (etiqueta anterior imprecisa: solo punto de montaje)
PILOT_GATE=BLOCKED_V2_LAYOUT_NOT_VERIFIED
```

**Diagnóstico:** el MASTER está en la arquitectura antigua 4 FUSE, sin configs aisladas de las dos cuentas ni los seis servicios v2 en producción. El preflight anterior rotuló `BIND_1..4=MOUNTED` únicamente por presencia de los destinos en mountinfo; esos cuatro destinos pueden ser los montajes FUSE legacy, NO bind. Se corrigió para usar `rclone_two_mount_health.check_two_fuse_four_bind(raw_mountinfo)`, que comprueba superblock, `fsroot`, `fstype`, origen, unicidad/no capas y correlación entre 2 FUSE y 4 binds. La nueva salida añade `V2_MOUNT_TOPOLOGY=NOT_VERIFIED|VERIFIED` y clasifica cada destino como `LEGACY_OR_UNVERIFIED`, `NOT_MOUNTED` o `VERIFIED_V2_BIND`. Nunca declarar la arquitectura v2 sana basándose solo en nombre de directorio. Tests regresión actualizados y ampliados; ejecución pendiente por operador.

El siguiente paso **no** es habilitar `RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER` ni `RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED`: ambos necesitan primero el corte controlado con `LocalAdapter` real, journal seguro, rollback y dos muestras de medios, que exige preparación independiente de este preflight. No inventar marcador `active`, no crear archivos `accountN.conf` a mano, no sobrescribir el rclone canónico, no interrumpir los cuatro montajes legacy solo para pasar un gate. `RELEASE_AUTHORIZED=NO`.

## Regresión de 980 tests confirmada por operador (19/11/2026)

Tras la corrección de detección de montajes legacy vs bind (V2_MOUNT_TOPOLOGY y clasificación LEGACY_OR_UNVERIFIED) y las pruebas adicionales, el operador confirmó: `Ran 980 tests in 1.421s` / `OK`. `GROUPED_PREFLIGHT_REGRESSION=PASS_980`. No equivale a un cutover físico del MASTER; la última inspección permanece `MODE=legacy`, `ACCOUNT1/2_CONFIG=MISSING_OR_UNSAFE`, unidades v2 inactivas. Próximo gate físico no intrusivo: `python3 /storage/.kodi/addons/service.cloud.masqelec/lib/rclone_two_mount_media_samples.py --inventory` en CoreELEC. No activar flags de primer arranque ni OAuth en esta fase. `RELEASE_AUTHORIZED=NO`.
