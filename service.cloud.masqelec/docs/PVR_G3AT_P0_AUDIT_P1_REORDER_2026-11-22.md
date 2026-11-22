# G3-AT — auditoría P0 y candidato de reordenación P1 (22/11/2026)

## Alcance
Únicamente laboratorio G3-AN/G3-AP, rama `develop`. G3-AB, G3-AM, Kodi habitual y producción inmutables. CoreELEC sin compilar.

## Evidencia del operador: preflight P0
- Rama `develop`, árbol limpio y HEAD local/remoto `050b64988af2b3af288039738daaf42f48bbf8c0` al comenzar.
- Contenedores G3-AN y G3-AP activos, G3-AB y G3-AM activos sin intervención; HTTP 39991 y HTSP 39992 abiertos.
- Kodi de laboratorio parado: `/tmp/g3ar-kodi-A3FZBaXx/data/userdata/Database/TV46.db` (53248 bytes). Baselines G3-AS y G3-AN presentes.
- Playlist anterior a G3-AT: CUID g3an-001 Alpha número 1 `http://g3ap-live:8080/ch1.ts`; CUID g3an-002 Beta número 2 `http://streams/ch2.ts`.
- Copia `/home/ubuntu/g3at-evidence/G3AT-P0-20261122T110403220259Z`: 37 archivos, SHA-256, `G3AT_SQLITE_INTEGRITY=ok`, `G3AT_BACKUP_VERIFY=PASS`. Config TVH copiada en caliente `LIVE_NON_ATOMIC`: no declarar restauración probada ni snapshot atómico.

## Auditoría de bajas: código fuente local
- `iptv_auto.c`: antes de parsear marca todos los muxes `im_delete_flag=1`; al hacer match CUID pone bandera a 0; con parse correcto `r==0` llama `mm->mm_delete(mm,1)` para ausentes; con error restaura banderas a 0. No se ha probado baja real todavía.
- `iptv_mux_delete` elimina configuración de mux persistido cuando `delconf=1`, luego `mpegts_mux_delete`; se pierde la correspondencia CUID↔UUID de mux eliminado salvo solución adicional.
- `service_destroy` llama `service_mapper_remove`, desvincula bouquets, servicios/canales; no llama directamente `channel_delete`.
- `channel_delete` envía `htsp_channel_delete` y elimina configuración `channel/config/<uuid>` con `delconf`; no demostrado que sea invocado por la baja automática del mux.
- `bouquet_remove_service` usa `bouquet_unmap_channel` si `delconf`. La rama completa y el resultado sobre HTSP/SQLite requieren experimento controlado. No inferir retención ni borrado de Kodi.
- `mpegts_mux_release` fue llamado por `mpegts_mux_delete`, pero su cuerpo no quedó capturado en la salida presentada. No afirmar su comportamiento interno sin inspección posterior.

## P1 candidato en GitHub (sin ejecución en laboratorio)
- `lab/pvr_g3ab/g3an/prepare.py`: nuevo stage `reorder`, genera Beta seguida de Alpha; conserva exactamente línea EXTINF, CUID, número y URL vigentes de `live`. No se modifican etapas previas ni el runtime hasta ejecución explícita.
- `tests/test_pvr_g3at_reorder.py`: pruebas de etapa `live`, orden inverso, URLs, CUID y números. No se han ejecutado aún en Ubuntu.
- Antes de operar: `git status --short`, `git pull --ff-only origin develop` con árbol limpio, `python3 -m unittest discover -s service.cloud.masqelec/tests -p test_pvr_g3at_reorder.py -v`, `git diff --check`; comprobar hash de playlist antes de cualquier escritura.
- P1 runtime pendiente: capturar API/HTSP/SQLite antes; escribir `prepare.py reorder` SOLO tras test PASS; esperar refetch G3-AN y capturar después. Reordenación posicional **no equivale a renumeración**, y no debe modificar `iUniqueId`, mux UUID, service UUID, channel UUID ni idChannel.
- No ejecutar `prepare.py live` de restauración sin gate posterior; no tratarla como rollback probado.

## Gates
- `G3AT_P0_INVENTORY=PASS` (de acuerdo con salida observada).
- `G3AT_P0_BACKUP=PASS` (hashes + SQLite; snapshot config no atómico).
- `G3AT_P0_STATIC_DELETE_AUDIT=PARTIAL` (ruta principal vista; cascada completa y comportamiento real todavía pendientes).
- `G3AT_P1_REORDER_SOURCE=COMMITTED_UNTESTED`.
- `G3AT_P1_RUNTIME=PENDING`.
- `G3AT_GAMMA_ADD_DELETE_READD=PENDING`.

No compilar, desplegar ni tocar el binario de TVH hasta nuevos gates.


## P1 — Evidencia real posterior (operador, 22/11/2026)

- Pruebas offline del generador: `Ran 3 tests ... OK`, `G3AT_P1_STATIC=PASS`, playlist `live` sin cambiar antes de la mutación.
- Baseline previo `G3AT_P1B_BASELINE=PASS`: muxes 2, servicios 3, canales 2; API TVH, HTSP v44 y copia íntegra de SQLite Kodi de laboratorio. Referencia `/home/ubuntu/g3at-evidence/G3AT-P1-before`.
- P1C ejecutado explícitamente en G3-AN: `prepare.py reorder` imprimió `G3AN_PLAYLIST_STAGE=REORDER`, `G3AN_PLAYLIST_PRIVATE_ONLY=YES`, `G3AT_P1C_PLAYLIST_ORDER=PASS`, `G3AT_P1C_CUID_AND_URL=PASS`.
- Tras 80 s, comparaciones API: `G3AT_P1C_MUXES_UUID_STABLE=True`, `G3AT_P1C_MUXES_COUNT_STABLE=True`, `G3AT_P1C_CUID_STABLE=True`, `G3AT_P1C_SERVICES_UUID_STABLE=True`, `G3AT_P1C_SERVICES_COUNT_STABLE=True`, `G3AT_P1C_CHANNELS_UUID_STABLE=True`, `G3AT_P1C_CHANNELS_COUNT_STABLE=True`, `G3AT_P1C_TVH_IDENTITY=PASS`.
- HTSP v44, `G3AQ_INITIAL_SYNC=PASS`, `G3AQ_HTSP_IDENTITY=PASS`; Alpha channelId `874874340`, UUID `e4852534cdb2fd64f54fd861d4d00767`, número 1; Beta channelId `1137851149`, UUID `0d3bd243f67184e9adb9ceadf4a51c50`, número 2.
- Log TVH tras mutación: `2026-11-22 11:17:44.788 [INFO] iptv: m3u parse: 0 new mux(es) in network 'IPTV LOCAL' (total 2)`. Evidencia de sincronización real, sin muxes nuevos.
- `G3AT_P1C_COMPARISON=PASS`, `G3AT_P1C_TVH_HTSP=PASS`. Evidencias bajo `/home/ubuntu/g3at-evidence/G3AT-P1-after`.
- **P1 no cerrado:** Kodi de laboratorio todavía no ha sido arrancado/re-sincronizado tras la reordenación y no se ha comparado la SQLite post-refresh. No declarar `G3AT_P1_KODI=PASS` ni `G3AT_P1_FINAL=PASS`.
- No se han tocado G3-AB, G3-AM, producción ni CoreELEC. Playlist actual: `reorder` (Beta primero, Alpha después); conservar hasta cerrar comparación Kodi o rollback explícito respaldado.

## P1D — Kodi aislado tras reordenación: identidad confirmada (22/11/2026)

El operador arrancó el Kodi aislado existente tras P1C y observó ambos canales. Cerró Kodi normalmente y ejecutó lectura SQLite en modo read-only. Evidencia:

```text
G3AT_P1D_KODI=CLOSED
SQLITE_INTEGRITY= ok
CHANNELS= [(1, 1, 874874340), (2, 1, 1137851149)]
```

Por tanto `G3AT_P1D_KODI_IDENTITY=PASS` para los registros `idChannel,iClientId,iUniqueId`. **Aún pendiente:** comparación estructural de clientes y asignaciones de grupos con `/home/ubuntu/g3at-evidence/G3AT-P1-before/TV46.db`. No proclamar `G3AT_P1_FINAL=PASS` hasta ese control. No se ha alterado directamente SQLite.


## G3-AT-P1E — Comparación SQLite final, PASS (operador, 22/11/2026)

La comparación read-only entre `G3AT-P1-before/TV46.db` y la base SQLite del Kodi aislado, tras reordenar Beta/Alpha y cerrar Kodi correctamente, devolvió:

```text
G3AT_P1E_CHANNELS_SCHEMA_STABLE=True
G3AT_P1E_CHANNELS_ROWS_STABLE=True
G3AT_P1E_CHANNELS_COUNT=2->2
G3AT_P1E_CLIENTS_SCHEMA_STABLE=True
G3AT_P1E_CLIENTS_ROWS_STABLE=True
G3AT_P1E_CLIENTS_COUNT=1->1
G3AT_P1E_CHANNELGROUPS_SCHEMA_STABLE=True
G3AT_P1E_CHANNELGROUPS_ROWS_STABLE=True
G3AT_P1E_CHANNELGROUPS_COUNT=4->4
G3AT_P1E_MAP_CHANNELGROUPS_CHANNELS_SCHEMA_STABLE=True
G3AT_P1E_MAP_CHANNELGROUPS_CHANNELS_ROWS_STABLE=True
G3AT_P1E_MAP_CHANNELGROUPS_CHANNELS_COUNT=6->6
G3AT_P1_SQLITE_COMPARISON=PASS
```

Sumado a P1B/P1C/P1D, `G3AT_P1_FINAL=PASS` para **reordenación meramente posicional con números explícitos constantes**. No se ha demostrado renumeración ni política de bajas. Estado de playlist en lab: `reorder`. G3-AB/G3-AM y producción protegidos; CoreELEC NO.

**Siguiente fase P2:** alta Gamma controlada con `CUID=g3an-003`, número propio 3, emisor existente y verificado (no asumir `/ch3.ts`). Auditar primero la política de auto-mapeo y la configuración G3-AN para evitar un alta de mux sin canal Kodi.


## G3-AT-P2A — Inventario previo al alta Gamma (22/11/2026)

Salida del operador, sin mutaciones: árbol local en `develop`, HEAD `193099a` (anterior a los commits documentales remotos); Kodi aislado `CLOSED`. Red IPTV LOCAL UUID `d1642fb49f8bf0d2c583ce1b2deae146`. API TVH: 2 muxes (Alpha CUID `g3an-001`, URL `http://g3ap-live:8080/ch1.ts`; Beta CUID `g3an-002`, URL `http://streams/ch2.ts`), 3 servicios, 2 canales. Servicio Beta histórico no vinculado: UUID `923fc082cf4b92edf42d4b5a87da125e`, `enabled=false`; otros dos servicios mantienen sus canales originales. G3-AP `server.py` permite únicamente rutas `/ch1.ts` y `/ch2.ts`, ninguna `/ch3.ts` todavía. No asumir fuente Gamma ni automapeo funcional.

**Gate P2A:** `INVENTORY=COLLECTED`, **no** `GAMMA_ADD=PASS`. Inspeccionar configuración API de mapeo de red y rutas de `service_mapper_process` antes de tocar el generador. Evitar una baja destructiva o crear duplicados en Gamma hasta contar con evidencia real de creación y asociación. G3-AB/G3-AM, producción y CoreELEC protegidos.


## G3-AT-P2B/P2C — Auditoría y candidato estático Gamma (22/11/2026)

Evidencia operador P2B: red G3-AN `autodiscovery=0`, `bouquet=True`, `scan_create=True`, `service_sid=1`, `channel_number=0`. En `service_mapper_process`, si no existe canal adecuado llama a `channel_create` y enlaza servicio/canal; sin embargo el alta efectiva sigue sin comprobarse. `bouquet_unmap_channel` elimina el canal mediante `channel_delete(ch,1)` cuando no hay otro servicio del mismo bouquet que lo mantenga. `bouquet_remove_service` llama a esa función con `delconf` activo. Por tanto la baja destructiva podría emitir HTSP `channelDelete` y borrar identidad persistida; la ejecución real en G3-AN/Kodi está PENDIENTE. No declarar recuperación de identidad tras reaparición.

Candidato P2C **solo código GitHub, no aplicado aún al runtime**:
- G3-AP `server.py` permite la URL sintética distinta `/ch3.ts` utilizando el archivo de prueba YA EXISTENTE `/source/ch1.ts` en modo solo lectura. No crear ni modificar fixtures G3-AB. La nueva ruta no estará activa hasta reinicio **solo del emisor G3-AP**, lo que interrumpe sus clientes; programarlo con preflight y sin reproducción activa.
- Generador privado G3-AN `prepare.py add-gamma` conserva exactamente las dos entradas completas del estado `reorder` y añade Gamma al final con `CUID=g3an-003`, `tvg-chno=3`, `tvh-chnum=3`, URL `http://g3ap-live:8080/ch3.ts`. No cambia etapas anteriores.
- Test offline `tests/test_pvr_g3at_gamma.py` comprueba invariantes, cantidad, URL única, CUID y línea original Alpha/Beta. **NO ejecutado** a fecha de escritura.
- P2C no autoriza todavía `prepare.py add-gamma`: primero `git pull --ff-only` con árbol limpio, pruebas estáticas PASS, preflight contenedor + HTTP de nueva ruta y comprobar estado de suscripciones de G3-AP/G3-AN. Sólo después, alta acotada G3-AN y observación de API/HTSP/Kodi.
- Mantener playlist activa en estado `reorder` hasta nuevo gate. No forzar `service_mapper` ni cambiar bouquets globalmente. No usar automáticamente etapa `reorder` como borrado seguro de Gamma tras su alta: podría ser DESTRUCTIVA.


## G3-AT-P2E — Emisor Gamma real, PASS (operador, 22/11/2026)

Tras preflight `G3AT_P2E_SUBSCRIPTIONS=0` y `G3AT_P2E_PREFLIGHT=PASS`, se recreó exclusivamente el contenedor `masqelec-pvr-g3ap-live-1` con `docker compose ... up -d --no-deps --force-recreate --pull never live`, necesaria por el bind mount de archivo único de server.py. El comando devolvió Started. HTTP local desde el propio contenedor:
```text
G3AT_P2E_CH1_HTTP=200
G3AT_P2E_CH1_BYTES=564
G3AT_P2E_CH1_TS_VALID=True
G3AT_P2E_CH3_HTTP=200
G3AT_P2E_CH3_BYTES=564
G3AT_P2E_CH3_TS_VALID=True
G3AT_P2E_MEDIA=PASS
G3AT_P2E_PROTECTED_CONTAINERS=PASS
G3AT_P2E_FINAL=PASS
```
Se compararon los ID de contenedores protegidos G3-AN/G3-AM/G3-AB antes y después sin diferencias. El ensayo de 3 paquetes TS en cada URL no equivale a prueba integral de reproducción. Gamma **aún no existe** en la playlist ni en TVH/Kodi. La playlist activa continúa `reorder`. Próximo gate `G3AT_P2F`: alta explícita Gamma con snapshot previo, comparación por UUID/CUID y revisión de mapeo; si solo se crea mux no declarar alta PVR PASS. No eliminar ni reañadir Gamma todavía.


## G3-AT-P2F — Alta real Gamma (operador, 22/11/2026)

Después de `G3AT_P2F_BASELINE=PASS` y snapshot previo `G3AT_P2F_SNAPSHOT_BEFORE=PASS`, se ejecutó una única mutación privada `prepare.py add-gamma` (`G3AN_PLAYLIST_STAGE=ADD-GAMMA`, `PRIVATE_ONLY=YES`). Tras 80 segundos:
- Entidades TVH `before={'muxes':2,'services':3,'channels':2}` → `after={'muxes':3,'services':4,'channels':3}`.
- `G3AT_P2F_MUXES_OLD_IDS_PRESERVED=True`, `G3AT_P2F_SERVICES_OLD_IDS_PRESERVED=True`, `G3AT_P2F_CHANNELS_OLD_IDS_PRESERVED=True`; ningún ID eliminado.
- Mux Gamma nuevo `aae864752fce1c09379c630a048f8f25`, CUID `g3an-003`, URL `http://g3ap-live:8080/ch3.ts`; servicio nuevo `095c73b01bb2a1c1f331f88aee1d3e20`; canal nuevo `0b86e3113c756785e2e976245c3101e1`.
- `G3AT_P2F_GAMMA_MUX=True`, `G3AT_P2F_EXISTING_IDENTITY=True`, `G3AT_P2F_MUX_GATE=PASS`.
- HTSP v44 `INITIAL_SYNC=PASS`, 3 canales: Gamma channelId `300123659`, UUID `0b86e3113c756785e2e976245c3101e1`, número 3; Alpha `874874340`, Beta `1137851149` estables.
- El comprobador histórico G3-AQ devolvió `G3AQ_HTSP_IDENTITY=FAIL` **porque exige `len==2`**. No representa una regresión demostrada. Se necesita sonda específica G3-AT.
- Log TVH `2026-11-22 11:26:44.789 iptv: m3u parse: 1 new mux(es) ... total 3`; `11:26:44.790 bouquet: ... G3AN Gamma/{PMT:0}: mapped service`; `11:27:44.789 0 new mux(es) ... total 3`.
- Evidencias `/home/ubuntu/g3at-evidence/G3AT-P2F`; `G3AT_P2F_EVIDENCE=COLLECTED`. **Pendientes**: comprobar explícitamente enlace servicio Gamma↔canal por API y nueva SQLite Kodi. No declarar `G3AT_P2_FINAL=PASS` todavía. No retirar ni reañadir Gamma, pues la baja puede ser destructiva.


## G3-AT-P2G — Enlace real Gamma servicio/canal, PASS (operador, 22/11/2026)

Comprobación API G3-AN de lectura, sobre UUID de P2F: mux `aae864752fce1c09379c630a048f8f25`, servicio `095c73b01bb2a1c1f331f88aee1d3e20`, canal `0b86e3113c756785e2e976245c3101e1`. Los 7 booleanos salieron `True`: `MUX_EXISTS`, `SERVICE_EXISTS`, `CHANNEL_EXISTS`, `CUID_CORRECT`, `SERVICE_LINKED_TO_CHANNEL`, `CHANNEL_LINKED_TO_SERVICE`, `CHANNEL_ENABLED`. `G3AT_P2G_MAPPING=PASS`.

La creación y asociación TVH está probada en G3-AN, pero **el cierre final de P2 requiere Kodi aislado**: confirmar 3 canales reales en SQLite, Alpha/Beta con filas y IDs conservados, Gamma nuevo `iUniqueId=300123659`, `iClientId=1`, sin duplicados, cliente y grupos sin degradación inesperada. No cambiar `add-gamma` ni quitar Gamma mientras se realiza esa prueba. No se han realizado bajas ni reapariciones.


## G3-AT-P2H — Gamma sincronizado en Kodi aislado, PASS (22/11/2026)

Tras ejecutar Kodi aislado y cerrarlo, el operador inspeccionó `TV46.db` en modo `ro`. Evidencia exacta:
```text
G3AT_P2H_SQLITE_INTEGRITY= ok
G3AT_P2H_CHANNELS= [(1, 1, 874874340), (2, 1, 1137851149), (3, 1, 300123659)]
G3AT_P2H_CLIENTS= [(1, 'pvr.hts')]
G3AT_P2H_GAMMA_IMPORTED= True
G3AT_P2H_EXISTING_IDS_STABLE= True
G3AT_P2H_SQLITE_GATE= PASS
```
Kodi retiene Alpha/Beta, añade Gamma con nueva identidad y conserva un único cliente. **Pendiente**: comparación de conjuntos de grupos, relaciones de grupos/canales y filas antiguas con P1-before; no exigir igualdad total de tablas porque el alta Gamma debe agregar filas. Aún no declarar `G3AT_P2_FINAL=PASS`. La playlist privada permanece `add-gamma` y no se ha realizado ninguna baja.


## G3-AT-P2I — Persistencia y cierre P2, PASS (22/11/2026)

El operador comparó por esquema y multiconjunto de filas SQLite en modo solo lectura el respaldo `/home/ubuntu/g3at-evidence/G3AT-P1-before/TV46.db` con el perfil Kodi aislado tras el alta Gamma. Evidencia:

```text
G3AT_P2I_CHANNELS_SCHEMA_STABLE=True
G3AT_P2I_CHANNELS_OLD_ROWS_PRESERVED=True
G3AT_P2I_CHANNELS_COUNT=2->3
G3AT_P2I_CHANNELS_ADDED=1
G3AT_P2I_CHANNELS_REMOVED_OR_CHANGED=0
G3AT_P2I_CLIENTS_SCHEMA_STABLE=True
G3AT_P2I_CLIENTS_OLD_ROWS_PRESERVED=True
G3AT_P2I_CLIENTS_COUNT=1->1
G3AT_P2I_CLIENTS_ADDED=0
G3AT_P2I_CLIENTS_REMOVED_OR_CHANGED=0
G3AT_P2I_CHANNELGROUPS_SCHEMA_STABLE=True
G3AT_P2I_CHANNELGROUPS_OLD_ROWS_PRESERVED=True
G3AT_P2I_CHANNELGROUPS_COUNT=4->4
G3AT_P2I_CHANNELGROUPS_ADDED=0
G3AT_P2I_CHANNELGROUPS_REMOVED_OR_CHANGED=0
G3AT_P2I_MAP_CHANNELGROUPS_CHANNELS_SCHEMA_STABLE=True
G3AT_P2I_MAP_CHANNELGROUPS_CHANNELS_OLD_ROWS_PRESERVED=True
G3AT_P2I_MAP_CHANNELGROUPS_CHANNELS_COUNT=6->9
G3AT_P2I_MAP_CHANNELGROUPS_CHANNELS_ADDED=3
G3AT_P2I_MAP_CHANNELGROUPS_CHANNELS_REMOVED_OR_CHANGED=0
G3AT_P2I_PERSISTENCE=PASS
```

**G3AT_P2_FINAL=PASS**: alta Gamma validada de M3U → TVH mux/servicio/canal → HTSP → Kodi SQLite, con retención de las filas antiguas y tres nuevas relaciones de grupos. Identidad Gamma: CUID `g3an-003`, mux `aae864752fce1c09379c630a048f8f25`, servicio `095c73b01bb2a1c1f331f88aee1d3e20`, canal `0b86e3113c756785e2e976245c3101e1`, HTSP/Kodi id `300123659`, Kodi idChannel `3`.

**Inicio P3 (eliminación y reaparición Gamma) NO AUTORIZADO aún**: eliminar CUID de playlist puede causar borrado de mux y canal vía bouquet; la reaparición quizá genere UUID/iUniqueId nuevos. No aplicar `prepare.py reorder`, no iniciar Kodi ni sincronizar borrado hasta obtener snapshot previo de TVH y copia SQLite verificada y examinar secuencia en dos fases. Proteger referencias G3-AB/G3-AM, Kodi habitual y CoreELEC. Estado activo `add-gamma`.


## G3-AT-P3A — Baja real Gamma TVH/HTSP, PASS (22/11/2026)

Preflight backup `/home/ubuntu/g3at-evidence/G3AT-P3-before` validado con hash de 5 ficheros: `TV46.db`, `playlist.m3u`, `muxes.json`, `services.json`, `channels.json`. Sin suscripciones activas y Kodi cerrado. Se ejecutó solo `g3an/prepare.py reorder`, quitando el CUID `g3an-003` de la playlist privada G3-AN.

Al refrescar Tvheadend:
```text
G3AT_P3A_MUXES_COUNT=2
G3AT_P3A_MUXES_GAMMA_PRESENT=False
G3AT_P3A_SERVICES_COUNT=3
G3AT_P3A_SERVICES_GAMMA_PRESENT=False
G3AT_P3A_CHANNELS_COUNT=2
G3AT_P3A_CHANNELS_GAMMA_PRESENT=False
G3AT_P3A_REFRESH_OBSERVED=True
G3AT_P3A_MUXES_OLD_PRESERVED=True
G3AT_P3A_SERVICES_OLD_PRESERVED=True
G3AT_P3A_CHANNELS_OLD_PRESERVED=True
G3AT_P3A_EXISTING_IDENTITY=PASS
G3AT_P3A_GAMMA_DELETION=PASS
G3AQ_HTSP_VERSION=44
G3AQ_INITIAL_SYNC=PASS
G3AQ_CHANNEL_COUNT=2
G3AQ_HTSP_IDENTITY=PASS
G3AT_P3A_EVIDENCE=COLLECTED
```
Para muxes, servicios y canales: `UNEXPECTED_NEW=[]` y `UNEXPECTED_LOST=[]`. Alpha HTSP `874874340` UUID `e4852534cdb2fd64f54fd861d4d00767` y Beta HTSP `1137851149` UUID `0d3bd243f67184e9adb9ceadf4a51c50` intactos. Log:
```text
2026-11-22 11:32:44.790 iptv: m3u parse: 0 new mux(es) ... (total 2)
2026-11-22 11:32:44.790 mpegts: playlist.m3u - G3AN Gamma ... - deleting
2026-11-22 11:32:44.790 bouquet: G3AN Gamma / IPTV LOCAL/.../Service01: unmapped from IPTV LOCAL
2026-11-22 11:32:44.790 channel: G3AN Gamma - deleting
2026-11-22 11:32:44.790 iptv: removed 1 mux(es) from network 'IPTV LOCAL'
```
Respaldo evidencias P3A `/home/ubuntu/g3at-evidence/G3AT-P3A/`, 7 ficheros con SHA256 verificados. **No concluir limpieza Kodi**: el Kodi aislado aún no ha sincronizado la baja. **No iniciar reaparición Gamma** hasta snapshot SQLite post-baja y revisión de grupos sin huérfanos. El estado actual de la playlist privada es `reorder`; Gamma ausente TVH.


## G3-AT-P3B — Sincronización baja Kodi y limpieza SQLite, PASS (22/11/2026)

Tras retirar Gamma de G3-AN/HTSP en P3A, el operador abrió el Kodi aislado, sincronizó la baja y cerró normalmente. Comparación SQLite read-only con `/home/ubuntu/g3at-evidence/G3AT-P1-before/TV46.db`:
```text
G3AT_P3B_CHANNELS_RESTORED=True
G3AT_P3B_CLIENTS_RESTORED=True
G3AT_P3B_CHANNELGROUPS_RESTORED=True
G3AT_P3B_MAP_CHANNELGROUPS_CHANNELS_RESTORED=True
G3AT_P3B_CHANNELS=[(1, 1, 874874340), (2, 1, 1137851149)]
G3AT_P3B_GAMMA_REMOVED=True
G3AT_P3B_SQLITE=PASS
G3AT_P3B_BACKUP=PASS
```
Respaldo de evidencia postbaja en `/home/ubuntu/g3at-evidence/G3AT-P3B/TV46-after-removal.db`, SQLite íntegra. Con el alcance de estas cuatro tablas, Kodi no dejó filas ni relaciones de Gamma tras su baja. **G3AT_P3B=PASS**; aún no hay evidencia de otras tablas no examinadas. Playlist activa `reorder`; TVH 2 mux / 3 servicios / 2 canales y HTSP 2 identidades originales. Siguiente P3C: reintroducir `add-gamma`, auditar nuevos UUID, mapeo bidireccional, HTSP y comprobar la ausencia de cambios en Alpha/Beta; reaparición Kodi como subgate posterior P3D. Prohibido asumir que los UUID de Gamma se conservan tras eliminación destructiva.


## G3-AT-P3C — Reaparición real Gamma TVH, PASS (22/11/2026)

El operador volvió a introducir Gamma usando exclusivamente `prepare.py add-gamma`, tras verificar respaldo P3A y estado TVH de dos canales. La verificación automatizada mostró:

```text
G3AT_P3C_BASELINE=PASS
G3AT_P3C_MUXES_NEW=['d74624c6a724a31e957e892acd2fb03e']
G3AT_P3C_MUXES_OLD_GAMMA_REUSED=False
G3AT_P3C_SERVICES_NEW=['bc650fd22d3cbb558cc38b1b0e6781a7']
G3AT_P3C_SERVICES_OLD_GAMMA_REUSED=False
G3AT_P3C_CHANNELS_NEW=['a1740c422bfc2d4166e4ebc6fa92cb4e']
G3AT_P3C_CHANNELS_OLD_GAMMA_REUSED=False
G3AT_P3C_MUXES_OLD_PRESERVED=True
G3AT_P3C_MUXES_ONE_NEW=True
G3AT_P3C_SERVICES_OLD_PRESERVED=True
G3AT_P3C_SERVICES_ONE_NEW=True
G3AT_P3C_CHANNELS_OLD_PRESERVED=True
G3AT_P3C_CHANNELS_ONE_NEW=True
G3AT_P3C_GAMMA_MUX=True
G3AT_P3C_GAMMA_BIDIRECTIONAL_MAPPING=True
G3AT_P3C_STABLE_REFRESH=True
G3AT_P3C_TVH=PASS
G3AT_P3C_EVIDENCE=PASS
```

TVH log 11:36:44 nuevo mux y mapeo bouquet; 11:36:59 fin de escaneo; 11:37:00 suscripción EPG. Evidencias con SHA256 bajo `/home/ubuntu/g3at-evidence/G3AT-P3C/`.

Hallazgo: conservar el CUID no recupera UUID de mux/servicio/canal tras borrado destructivo. UUID original Gamma mux `aae864752fce1c09379c630a048f8f25` → nuevo `d74624c6a724a31e957e892acd2fb03e`; servicio `095c73b01bb2a1c1f331f88aee1d3e20` → `bc650fd22d3cbb558cc38b1b0e6781a7`; canal `0b86e3113c756785e2e976245c3101e1` → `a1740c422bfc2d4166e4ebc6fa92cb4e`. Alpha/Beta UUID íntegros.

**P3D pendiente**: inspección HTSP nueva `channelId` numérica, sincronización Kodi aislado, confirmación de 3 canales sin duplicados, cliente/grupos y ausencia del `iUniqueId=300123659` original de Gamma, salvo reutilización demostrada. No declarar `G3AT_P3_FINAL=PASS` aún. Playlist actual `add-gamma`.


## G3-AT-P3D / P3 FINAL — Reaparición Gamma en Kodi, PASS (22/11/2026)

Operador ejecutó el gate de reaparición tras P3C, obtuvo y usó identidad HTSP nueva de Gamma para contrastarla con la SQLite del Kodi aislado tras sincronización y cierre. Salida exacta entregada:
```text
G3AT_P3D_CHANNELS_COUNT=2->3
G3AT_P3D_CLIENTS_COUNT=1->1
G3AT_P3D_CHANNELGROUPS_COUNT=4->4
G3AT_P3D_MAP_CHANNELGROUPS_CHANNELS_COUNT=6->9
G3AT_P3D_THREE_CHANNELS=True
G3AT_P3D_ALPHA_BETA_STABLE=True
G3AT_P3D_GAMMA_RECREATED=True
G3AT_P3D_PVR_CLIENT_STABLE=True
G3AT_P3D_CHANNELS_OLD_PRESERVED=True
G3AT_P3D_CLIENTS_OLD_PRESERVED=True
G3AT_P3D_CHANNELGROUPS_OLD_PRESERVED=True
G3AT_P3D_MAP_CHANNELGROUPS_CHANNELS_OLD_PRESERVED=True
G3AT_P3D_CHANNELS= [(1, 1, 874874340), (2, 1, 1137851149), (3, 1, 1108112545)]
G3AT_P3D_GAMMA_OLD_ID_ABSENT= True
G3AT_P3D_FINAL=PASS
G3AT_P3D_BACKUP=PASS
```
Gamma anterior HTSP/Kodi `300123659`, nuevo `1108112545`: la reaparición produce identidad numérica diferente. Alpha `874874340` y Beta `1137851149` sin cambio. Nuevos UUID TVH P3C: mux `d74624c6a724a31e957e892acd2fb03e`, servicio `bc650fd22d3cbb558cc38b1b0e6781a7`, canal `a1740c422bfc2d4166e4ebc6fa92cb4e`. Cliente PVR único y grupos antiguos preservados, 3 nuevas relaciones tras reaparición. SQLite comprobada íntegra y copia en `/home/ubuntu/g3at-evidence/G3AT-P3D/TV46-after-reappearance.db`.

**G3AT_P3_FINAL=PASS** para ciclo controlado alta–baja–reaparición, incluyendo TVH/HTSP/Kodi y comparación de cuatro tablas SQLite. El CUID protege continuidad de mux si la entrada permanece, pero no obliga a reutilizar UUID después de borrado destructivo. Una playlist temporalmente incompleta podría destruir identidades. **No extrapolar a playlists grandes, actualización interrumpida, reinicios ni reproducción activa**. G3-AB/G3-AM, Kodi habitual, sistema producción y CoreELEC no se han tocado. Estado activo de G3-AN: playlist `add-gamma`, 3 canales.

### Próximo diseño recomendado (pendiente de implementación y pruebas)

Antes de modificar el código del addon, especificar política de reconciliación con M3U autoritativa y transacción de cambios: distinguir actualizaciones por CUID de bajas auténticas; validar lista completa y evitar aplicar listas parciales/vacías; definir tratamiento de canales retirados y casos de error; realizar pruebas de estrés y cortes de sincronización sin alterar directamente la SQLite de Kodi. El escenario actual demuestra la semántica de TVH y Kodi, no la política del addon.
