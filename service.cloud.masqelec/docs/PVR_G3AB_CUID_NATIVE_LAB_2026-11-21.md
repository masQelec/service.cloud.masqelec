# G3-AB — laboratorio independiente para persistencia de identidad CUID (2026-11-21)

## Alcance

G3-AA dispone de **15 pruebas offline PASS**. El formato actual de la playlist remota fue inspeccionado en la rama predeterminada de `masQelec/cloud.masqelec`: 865 `#EXTINF`, 865 `CUID` presentes y únicos; no confundir con la observación histórica de 720 canales en master. G3-Z5 ha demostrado que un servicio inactivo sin canal puede compartir mux con servicios de canales existentes. Ninguno de esos resultados demuestra que TVH interprete CUID ni que Kodi lo preserve.

G3-AB usa el nuevo directorio `lab/pvr_g3ab` con:
- Compose **nuevo proyecto** `masqelec-pvr-g3ab`, puertos HTTP/HTSP **solo loopback 19991/19992**, otro `runtime/tvh_config` totalmente separado de G3-W, Nginx de streams sintéticos y sin volúmenes de master.
- `prepare.py` escribe únicamente `lab/pvr_g3ab/runtime/playlist/playlist.m3u` con dos CUID estables `g3ab-001` y `g3ab-002` en atributos `CUID` entrecomillados; nombres, grupos y URL son sintéticos.
- Alternativa `ch1-alt.ts` es una copia del mismo TS, pero cambia la URL en la M3U; evita cambiar a la vez el contenido audiovisual y la URL.
- Seis variaciones con CUID idénticos y un estado restaurado.
- `tests/test_pvr_g3ab_fixture.py`: 16 casos sintéticos. **No declarar PASS antes de que Ubuntu los ejecute**.

## Etapas independientes

Cada etapa parte de los atributos de **baseline** y cambia una única dimensión, salvo `restored` que la restaura completamente:

| Etapa | Acción | Expectativa de prueba, aún NO demostrada |
| --- | --- | --- |
| `baseline` | Dos canales con CUID distintos | Registrar UUID TVH y channelid Kodi |
| `rename` | Renombrar el primero | Comprobar UUID/IDs y nombre |
| `url` | Cambiar la URL del primero | Comprobar si se regenera mux, servicio y/o canal |
| `group` | Cambiar grupo del primero | Comprobar categorías y grupo original |
| `reorder` | Invertir orden M3U sin cambiar `tvg-chno` | Comprobar numeración y IDs, sin asumir reorder Kodi |
| `homonym` | Ambos nombres iguales, CUID distintos | Observar si TVH confunde o conserva dos identidades |
| `restored` | M3U idéntica a `baseline` | Comprobar si identificadores recuperan estado |

## Preparación Ubuntu

Ejecutar comandos **solo** en Ubuntu de laboratorio:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/lab/pvr_g3ab/prepare.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ab_fixture.py' -v

cd service.cloud.masqelec/lab/pvr_g3ab
docker compose config --quiet
python3 prepare.py baseline
docker compose up -d
docker compose ps
```

TVH G3-AB en `http://127.0.0.1:19991`. Crear red Automatic IPTV **exclusiva** para el laboratorio G3-AB apuntando a `file:///lab_playlist/playlist.m3u`, configurar su refetch y mapeo de servicios, y comprobar dos canales. No conectar este TVH a producción.

**Kodi:** usar `runtime/kodi_home` como perfil separado y configurar `pvr.hts` para conectar **solo a 127.0.0.1:19992**. No abrir G3-W Kodi y G3-AB Kodi simultáneamente; pueden competir por servidor web puerto 8080 o por el perfil activo. Aislar también la configuración HTTP; si se habilita JSON-RPC HTTP, proteger el acceso: previamente se observó que Kodi abría `0.0.0.0:8080` y `[::]:8080`. No asumir que establecer `HOME` prueba aislamiento absoluto del perfil; verificar rutas reales de userdata y la conexión pvr.hts antes de proceder. Pueden utilizarse puertos HTTP diferentes, pero no se da por configurado un 8081 inexistente.

## Validación funcional, por etapas

1. Registrar **baseline** de canal TVH (UUID, nombre sintético, servicios) por `http://127.0.0.1:19991/api/channel/grid` y Kodi con `PVR.GetChannels` vía su JSON-RPC de lectura.
2. Cambiar `python3 prepare.py rename`; **esperar relectura efectiva**, volver a obtener ambas listas, comparar UUID/IDs. Si no cambia el nombre, no asumir que TVH ignora CUID: distinguir refresco fallido.
3. Repetir por separado `url`, `group`, `reorder`, `homonym`, **`restored`**, registrando los IDs y qué atributos cambiaron. La salida de `prepare.py` confirma solo el nuevo archivo.
4. Ante identificación ambigua, desaparición de canales, errores de TVH o Kodi, parar el gate y conservar snapshots. No limpiar SQLite ni manipular servicios/muxes.
5. No afirmar que CUID es soportado por TVH hasta que exista evidencia específica de lectura de dicho atributo; estabilidad de UUID ante modificaciones es solo comportamiento observado, no causalidad CUID.

`G3AB_LAB_CREATED=YES`; `G3AB_UNIT_TESTS=PENDING`; `G3AB_NATIVE_IDENTITY=NOT_TESTED`; `CUTOVER_AUTHORIZED=NO`; `PRODUCTION_TOUCHED=NO`.


## Arranque inicial comunicado por el operador — 2026-11-21

```text
G3AB_STAGE=BASELINE
G3AB_CUID_COUNT=2
G3AB_MASTER_UNTOUCHED=YES
G3AB_G3W_UNTOUCHED=YES
Docker network masqelec-pvr-g3ab_pvr_g3ab created
masqelec-pvr-g3ab-streams-1 Up (80/tcp interno)
masqelec-pvr-g3ab-tvh-1 Up (127.0.0.1:19991->9981/tcp, 127.0.0.1:19992->9982/tcp)
```

Estado `G3AB_COMPOSE_STARTED=YES`, `G3AB_BASELINE_FILE_WRITTEN=YES`, `G3AB_UNIT_TESTS=NOT_REPORTED`, `G3AB_TVH_CHANNELS=NOT_YET_VERIFIED`, `G3AB_KODI_CHANNELS=NOT_YET_VERIFIED`. Puertos publicados en localhost, sin evidencia de lectura efectiva por TVH o mapeo a canales. Siguiente paso: configurar Automatic IPTV apuntando exclusivamente a `file:///lab_playlist/playlist.m3u`, mapear dos servicios, consultar el baseline de TVH por API y luego conectar perfil Kodi aislado. No ejecutar etapa `rename` antes de registrar ambos snapshots.


## Baseline real: BLOQUEADO por duplicado de canal (2026-11-21)

Tras configurar IPTV automático en el TVH aislado G3-AB, el operador consultó `GET /api/channel/grid` y observó:

```text
UUID: f08f75aa26b58386630d4b225adbb34f NOMBRE: G3AB Beta
UUID: e2bf26af3bd98f7ac3f11acb11ce12cc NOMBRE: G3AB Beta
UUID: 185e5bdda6aafa6aa1aad2bb94ee703a NOMBRE: G3AB Alpha
TOTAL: 3
```

La playlist sintética generada tiene **2** entradas con CUID distintos. El TVH aislado presenta **3** UUID de canal, con dos nombres Beta idénticos. `G3AB_TVH_BASELINE=BLOCKED_3_FOR_2`, `G3AB_TVH_DUPLICATE_NAME=YES`, `G3AB_TVH_DUPLICATE_CUID_PROVEN=NO`. El duplicado de nombre no demuestra que ambos canales estén asociados al mismo servicio, ni que TVH lea CUID, ni que uno sea eliminable.

**Gate cerrado:** no ejecutar `prepare.py rename`, no conectar Kodi todavía, no borrar canal por nombre, no tocar master ni SQLite. Investigar por GET los campos `channel/grid` (`uuid`, `name`, `number`, `services`, `bouquet`, `enabled`, `tags`) y comparar las referencias contra `mpegts/service/grid`; imprimir solo campos de laboratorio, nunca URL o credenciales. Diferenciar mapeo duplicado manual/automático, persistencia de un servicio y dos canales distintos. No corregir manualmente sin documentar primero causa y mecanismo.


## Segunda consulta G3-AB: 3→2 canales observados; causa aún no probada

El operador repitió GET `channel/grid` y `mpegts/service/grid` tras observar inicialmente dos `G3AB Beta`. Esta vez informó:

```text
G3AB Beta  UUID=f08f75aa26b58386630d4b225adbb34f  number=2  enabled=True  service=afe6f317e9b95eb03f6d91691e80f537  SID=2  MUX=355a43f5f4c718478b87d3b6a1bc8408
G3AB Alpha UUID=185e5bdda6aafa6aa1aad2bb94ee703a number=1 enabled=True service=18cd0031a734c2342ac3956d754fb63e SID=1 MUX=4d3f4f0b654e570dc39029bebaf5c555
CANALES=2
SERVICIOS_MPEGTS=3
SERVICIOS_COMPARTIDOS_POR_VARIOS_CANALES=0
```

El UUID `e2bf26af3bd98f7ac3f11acb11ce12cc` (segundo Beta en el primer GET) **ya no aparece en channel/grid**. No se acreditó cuándo ni por qué desapareció. Es compatible con convergencia asíncrona, pero no demuestra causalidad ni confirma que una sola ejecución de la playlist produzca un canal por CUID. Hay 3 servicios MPEG-TS, sin información todavía de cuál está huérfano. `G3AB_TVH_CURRENT_INVENTORY=2`, `G3AB_TVH_BASELINE_STABILITY=NOT_YET_PROVEN`, `G3AB_KODI_BASELINE=NOT_TESTED`.

Antes de avanzar: comparar varias instantáneas READ-ONLY de 2 canales, los mismos UUID, mismas referencias de servicio, misma M3U baseline; investigar si tercer servicio está sin canal; y comprobar que las 16 pruebas unitarias pasan. No borrar canales/servicios/muxes ni activar variante `rename` hasta fijar la línea base.


## G3-AB baseline estabilizado por tres GET de solo lectura (operador, 2026-11-21)

El operador ejecutó tres consultas `GET /api/channel/grid` separadas por intervalos de 20 s y comparó tuplas `(uuid, name, services)`:

```text
LECTURA_1_CANALES: 2
LECTURA_1_UUID: ['185e5bdda6aafa6aa1aad2bb94ee703a', 'f08f75aa26b58386630d4b225adbb34f']
LECTURA_2_CANALES: 2
LECTURA_2_UUID: ['185e5bdda6aafa6aa1aad2bb94ee703a', 'f08f75aa26b58386630d4b225adbb34f']
LECTURA_3_CANALES: 2
LECTURA_3_UUID: ['185e5bdda6aafa6aa1aad2bb94ee703a', 'f08f75aa26b58386630d4b225adbb34f']
INVENTARIO_ESTABLE: True
SERVICIOS_TOTALES: 3
SERVICIOS_SIN_CANAL: 1
```

Correspondencia TVH del snapshot anterior: `G3AB Alpha`→`185e5bdda6aafa6aa1aad2bb94ee703a`; `G3AB Beta`→`f08f75aa26b58386630d4b225adbb34f`. El script comparó también nombre y servicios, aunque solo imprimió UUID. El tercer UUID Beta previo `e2bf26af3bd98f7ac3f11acb11ce12cc` ya no aparece. Conclusión acotada: `G3AB_TVH_BASELINE_STABLE_3_READS=PASS`; no se ha acreditado por qué surgió/desapareció el duplicado, ni estabilidad tras modificación de playlist. Se conserva un servicio MPEG-TS sin canal y no se autoriza eliminarlo.

Próximo gate: **Kodi G3-AB aislado**, comprobar userdata efectiva y host HTSP 127.0.0.1:19992 (nunca 19982 de G3-W ni master), registrar dos `channelid` con `PVR.GetChannels`, y solo después ensayar `rename`. Las 16 pruebas unitarias del fixture G3-AB no constan aún reportadas por el operador.


## Incidencia de perfil Kodi / puerto de laboratorio (operador, 2026-11-21)

El operador indicó que **olvidó cambiar los puertos de Kodi y seguía con los del laboratorio anterior**. Una consulta JSON-RPC arrojó:
```text
KODI_ID: 2 NOMBRE: G3AB Alpha NUMERO: 1
KODI_ID: 1 NOMBRE: G3AB Beta NUMERO: 2
TOTAL: 2
```
**No validar aún la identidad Kodi G3-AB** con este snapshot: la declaración del operador sobre el puerto/configuración requiere verificar que `pvr.hts` está conectado efectivamente a `127.0.0.1:19992` y no `19982` del laboratorio G3-W, ni a otro cliente PVR. Los nombres visibles podrían ser persistidos en caché/configuración previa; la respuesta JSON-RPC por sí sola no revela el servidor de procedencia. Reiniciar solo Kodi del perfil `runtime/kodi_home` tras corregir/confirmar el endpoint y repetir la consulta de lectura; no borrar `TVxx.db`. Marcar `G3AB_KODI_BASELINE=BLOCKED_PENDING_ENDPOINT_PROOF`; no ejecutar `rename`.


## Segunda lectura de Kodi tras indicación de revisar puerto

El operador comunicó otro GET JSON-RPC `PVR.GetChannels(channelgroupid=alltv)`:

```text
ID: 2 NOMBRE: G3AB Alpha
ID: 1 NOMBRE: G3AB Beta
TOTAL: 2
```

Los IDs y etiquetas son **idénticos** a la lectura anterior. Esto comprueba estabilidad entre esas dos respuestas, pero **no** la conexión efectiva al HTSP `127.0.0.1:19992`: el usuario no ha confirmado explícitamente qué puerto dejó configurado, ni JSON-RPC expone la procedencia. Siguiente gate leer conexiones TCP reales del proceso Kodi y comprobar `127.0.0.1:19992` ESTAB y ausencia de `127.0.0.1:19982` ESTAB. No repetir innecesariamente PVR.GetChannels ni ejecutar `rename` antes de confirmar el endpoint.


## G3-AB: conexión HTSP de Kodi al laboratorio confirmada por socket (2026-11-21)

Operador ejecutó en Ubuntu `sudo ss -tnp state established '( dport = :19992 or dport = :19982 )'` con Kodi abierto. Resultado:

```text
Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
0      0 127.0.0.1:57906    127.0.0.1:19992 users:(("kodi.bin",pid=182136,fd=34))
```

La **conexión TCP observada** termina en `127.0.0.1:19992`, HTSP del proyecto G3-AB; no hay conexión mostrada a 19982 en este filtro. La consulta JSON-RPC anterior muestra `G3AB Alpha`→`channelid=2`, `G3AB Beta`→`channelid=1`, ambos con nombres de G3-AB. La lectura TVH estable 3 veces registró Alpha UUID `185e5bdda6aafa6aa1aad2bb94ee703a`, Beta UUID `f08f75aa26b58386630d4b225adbb34f`.

`G3AB_KODI_HTSP_PORT=VERIFIED_19992`, `G3AB_TVH_BASELINE_2=PASS`, `G3AB_KODI_BASELINE_2=PASS`, `G3AB_RENAME_STAGE=NOT_YET_EXECUTED`, `G3AB_CUID_CAUSALITY=NOT_PROVEN`. Esta evidencia verifica el socket y el contenido PVR observado, no demuestra que TVH reconozca el atributo CUID. Próximo gate: ejecutar `prepare.py rename` y esperar refetch confirmado; observar UUID y channelid, número de canales y nombre final, sin borrar datos ni tocar producción.


## G3-AB rename: archivo cambiado, sin propagación observada (operador, 2026-11-21)

El operador ejecutó `python3 prepare.py rename`; herramienta informó:
```text
G3AB_STAGE=RENAME
G3AB_CUID_COUNT=2
G3AB_MASTER_UNTOUCHED=YES
G3AB_G3W_UNTOUCHED=YES
```
Consulta posterior de solo lectura:
```text
=== TVHEADEND ===
UUID: 185e5bdda6aafa6aa1aad2bb94ee703a NOMBRE: G3AB Alpha
UUID: f08f75aa26b58386630d4b225adbb34f NOMBRE: G3AB Beta
TOTAL: 2
=== KODI ===
ID: 2 NOMBRE: G3AB Alpha
ID: 1 NOMBRE: G3AB Beta
TOTAL: 2
```
`G3AB_RENAME_PLAYLIST_WRITTEN=YES`; `G3AB_RENAME_PROPAGATED=NO_OBSERVED`; `G3AB_TVH_UUID_UNCHANGED=YES`; `G3AB_KODI_ID_UNCHANGED=YES`; `G3AB_REFETCH_CONFIRMED=NO`; `G3AB_CUID_CAUSALITY=UNPROVEN`. **No afirmar** que TVH rechaza rename hasta comprobar que leyó la M3U nueva y distinguir el nombre del servicio del nombre de canal, que puede estar gestionado manualmente/por configuración. Detener variaciones posteriores mientras se investiga. No reiniciar TVH ni modificar DB o master.


## G3-AB rename: nombre nuevo ya visible en TVH (consulta posterior)

El operador realizó un nuevo diagnóstico de solo lectura tras el snapshot anterior en el que el nombre seguía antiguo:

```text
=== PLAYLIST ===
NOMBRE_NUEVO_EN_M3U: True
NOMBRE_ANTIGUO_EN_M3U: False
=== CANALES ===
NOMBRE: G3AB Beta
AUTONAME: True
BOUQUET: True
SERVICIOS: 1
---
NOMBRE: G3AB Alpha Renamed
AUTONAME: True
BOUQUET: True
SERVICIOS: 1
---
=== MULTIPLEXORES ===
MUX_NOMBRE: playlist.m3u - G3AB Beta
MUX_HABILITADO: 1
---
MUX_NOMBRE: playlist.m3u - G3AB Alpha
MUX_HABILITADO: 1
```

**Corrección de la interpretación previa:** `G3AB_RENAME_PROPAGATED=YES_TVH_OBSERVED`. En el snapshot inmediatamente posterior a `prepare.py rename` no había cambiado ningún nombre, pero en la consulta posterior el canal ya aparece renombrado. No está demostrado el instante exacto, el trigger de relectura ni el tiempo hasta convergencia. `autoname=True` y `bouquet=True` en ambos canales; **el nombre del mux Alpha permanece con la etiqueta anterior**, lo que no implica falta de propagación al canal. Este diagnóstico no imprimió UUID de canales ni estado Kodi; por tanto `G3AB_RENAME_TVH_UUID_STABLE=NOT_RECHECKED` y `G3AB_RENAME_KODI_ID_STABLE=NOT_RECHECKED` en el punto actual. Próximo gate: obtener snapshots TVH UUID+nombre y Kodi ID+nombre; no ejecutar etapa URL hasta confirmación de ambos.


## G3-AB: logs TVH durante rename, refetch periódico observado (2026-11-21)

El operador aportó logs de Tvheadend con entradas `iptv: m3u parse: 0 new mux(es) in network 'IPTV LOCAL' (total 2)` aproximadamente cada minuto, de **11:51:09 a 12:05:09**. Esto confirma procesamiento periódico de la playlist y ausencia de nuevos muxes en esos instantes; no mide el momento exacto en que el nuevo nombre apareció ni por sí mismo prueba identidad de TVH/Kodi o reconocimiento de CUID.

Aparecen además avisos `epggrab: EIT/PSIP data completion timeout` para G3AB Beta (11:56:50) y errores HTTP `/imagecache/1` y `/imagecache/2` con estado 404 (11:58). Son señales secundarias de EPG/imágenes sintéticas; no está demostrado que tengan relación con el rename. No corregirlas con cambios destructivos ni confundirlas con el gate de identidad.

Estado: `G3AB_REFETCH_PERIODIC_LOG=OBSERVED`; `G3AB_NEW_MUXES=0`; `G3AB_RENAME_TVH_VISIBLE=YES` por lectura anterior; `G3AB_RENAME_UUID_STABLE=NOT_YET_RECHECKED`; `G3AB_RENAME_KODI_ID_STABLE=NOT_YET_RECHECKED`; `G3AB_CUID_CAUSALITY=NOT_PROVEN`. Próximo paso: consulta puntual UUID+nombre del TVH y channelid+nombre del Kodi sin cambiar etapas.


## G3-AB rename: TVH OK, Kodi mantiene channelid pero no refleja nuevo nombre (2026-11-21)

El operador ejecutó lectura conjunta y reportó:

```text
TVH_TOTAL: 2
KODI_TOTAL: 2
TVH_ALPHA_UUID_STABLE: True
TVH_ALPHA_RENAMED: True
KODI_ALPHA_ID_STABLE: True
KODI_ALPHA_RENAMED: False
```

`G3AB_RENAME_TVH_UUID_STABLE=PASS`, `G3AB_RENAME_TVH_NAME=PASS`, `G3AB_RENAME_KODI_CHANNELID_STABLE=PASS`, `G3AB_RENAME_KODI_LABEL=FAIL_CURRENT_SNAPSHOT`. Se confirma preservación observada de UUID/canal ID ante rename con CUID estable, **pero no** que CUID sea la causa. No afirmar convergencia global ni que Kodi refresque automáticamente los metadatos: la identidad y el nombre se comportan de forma distinta. Se requiere examinar la etiqueta efectiva, el estado de propagación y las opciones de Kodi/pvr.hts sin modificar `TVxx.db` ni saltar al escenario `url`.

El diagnóstico seguro es consultar otra vez Kodi y TVH, verificar socket HTSP 19992 si necesario, y revisar si el nombre está fijado en Kodi o si requiere una actualización no destructiva de la conexión PVR. Evitar recomendaciones de desactivar/habilitar pvr.hts hasta saber si la sincronización eventual actualiza por sí sola; documentar el resultado de cada intervención.


## G3-AB: Kodi etiqueta anterior confirmada; investigar HTSP channelUpdate (2026-11-21)

Última salida reportada por el operador a través de JSON-RPC del perfil Kodi G3-AB:

```text
ID: 2
NOMBRE: G3AB Alpha
---
ID: 1
NOMBRE: G3AB Beta
```

El TVH de laboratorio ya presentaba `G3AB Alpha Renamed` y su UUID preservado. **No hay convergencia de etiqueta en Kodi**, aunque se conservaron 2 canales y el ID 2. El protocolo HTSP documenta la notificación **`channelUpdate`** con campo opcional `channelName`, así como el mecanismo de metadatos asíncronos: https://docs.tvheadend.org/documentation/development/htsp/server-to-client-methods y https://docs.tvheadend.org/documentation/development/htsp/client-to-server-rpc-methods. La existencia del mecanismo **no demuestra** que TVH emitiera efectivamente el evento ni que pvr.hts lo procesara.

`G3AB_RENAME_TVH=PASS`; `G3AB_RENAME_KODI_LABEL=FAIL_CURRENT_STATE`; `G3AB_RENAME_KODI_ID=STABLE`; `G3AB_HTSP_CHANNEL_UPDATE_SEEN=NOT_TESTED`. Próxima prueba de diagnóstico **sin limpiar base de datos ni resetear el cliente**: cerrar solo Kodi de laboratorio y reiniciarlo con el mismo HOME G3-AB, verificar el socket al puerto 19992 y consultar otra vez PVR.GetChannels para distinguir reimportación inicial de actualización en vivo. No seguir con `prepare.py url` mientras el rename no se resuelva. Si reiniciar Kodi corrige la etiqueta, hay un fallo de actualización en vivo o notificación (no necesariamente del lado TVH); si sigue incorrecta, investigar opciones de nombres locales y persistencia de metadatos de Kodi sin borrar `TVxx.db`.


## G3-AB rename: Kodi muestra el nuevo nombre tras reinicio normal (operador, 2026-11-21)

Después de cerrar y reiniciar **únicamente Kodi G3-AB** con el mismo perfil `runtime/kodi_home`, sin limpieza de TVxx.db, sin deshabilitar pvr.hts y sin eliminar canales, el operador reportó:

```text
ID: 2 NOMBRE: G3AB Alpha Renamed
ID: 1 NOMBRE: G3AB Beta
```

TVH previamente confirmó `G3AB Alpha Renamed` con UUID `185e5bdda6aafa6aa1aad2bb94ee703a`; Kodi mantiene ID `2`. `G3AB_RENAME_TVH=PASS`, `G3AB_RENAME_KODI_AFTER_RESTART=PASS`, `G3AB_RENAME_IDS_STABLE=YES_OBSERVED`, `G3AB_KODI_LIVE_NAME_REFRESH=NOT_OBSERVED`, `G3AB_HTSP_CHANNELUPDATE_CAUSE=UNPROVEN`, `G3AB_CUID_CAUSALITY=UNPROVEN`.

**Control metodológico antes de G3-AB URL:** `prepare.py url` restaura los metadatos `name`/`group` del baseline al mismo tiempo que cambia la URL, por diseño de etapas independientes. Por tanto, NO transicionar directamente `rename → url`: ejecutar `prepare.py restored`, esperar convergencia TVH/Kodi y confirmar el nombre original `G3AB Alpha` con los identificadores conservados. Solo entonces ejecutar `prepare.py url`. Si el nombre de Kodi no vuelve a baseline en vivo, reiniciar solo Kodi de laboratorio y registrar el hecho; no borrar SQLite ni datos PVR. Tampoco se debe interpretar la estabilidad de UUID ante URL como prueba del uso causal de CUID.


## G3-AB: etapa restored escrita por el operador; convergencia pendiente

El operador ejecutó `python3 prepare.py restored` y obtuvo:

```text
G3AB_STAGE=RESTORED
G3AB_CUID_COUNT=2
G3AB_MASTER_UNTOUCHED=YES
G3AB_G3W_UNTOUCHED=YES
```

Esto verifica **solo la salida del generador y su declaración de ámbito**, no confirma aún que TVH haya releído la M3U restaurada ni que Kodi haya recuperado `G3AB Alpha`. El snapshot esperado sigue siendo Alpha UUID `185e5bdda6aafa6aa1aad2bb94ee703a` / Kodi `2`, Beta UUID `f08f75aa26b58386630d4b225adbb34f` / Kodi `1`; inventarios 2/2. `G3AB_RESTORED_FILE_WRITTEN=YES`, `G3AB_RESTORED_TVH=NOT_YET_VERIFIED`, `G3AB_RESTORED_KODI=NOT_YET_VERIFIED`, `G3AB_URL_STAGE=BLOCKED_PENDING_RESTORED_BASELINE`. No cambiar todavía a `prepare.py url`.


## G3-AB restored: TVH vuelve al baseline, Kodi Alpha aún obsoleto (operador, 2026-11-21)

Consulta de lectura conjunta tras `prepare.py restored`:

```text
TVH_TOTAL: 2
KODI_TOTAL: 2
ALPHA_TVH_OK: True
ALPHA_KODI_OK: False
BETA_TVH_OK: True
BETA_KODI_OK: True
```

`G3AB_RESTORED_TVH=PASS`; `G3AB_RESTORED_KODI_ALPHA=FAIL_LIVE`; `G3AB_RESTORED_KODI_BETA=PASS`. Ya había ocurrido la falta de propagación de la etiqueta al entrar en `rename`, resuelta entonces mediante cierre/reinicio normal de Kodi aislado, sin borrar `TVxx.db`. Diagnóstico propuesto: repetir reconexión normal del perfil G3-AB sin alterar TVH/M3U, verificar HTSP puerto 19992 y PVR.GetChannels. Si Alpha vuelve a `G3AB Alpha` con `channelid=2`, registrar `G3AB_RESTORED_KODI_AFTER_RESTART=PASS`. No pasar a `url` antes de confirmarlo. El patrón apoya un defecto de refresco en vivo del nombre, pero no identifica aún componente causal.


## G3-AB restored: operador informa actualización al reiniciar PVR, sin reiniciar Kodi completo

El operador aclara que **en Kodi, al reiniciar PVR sí se produjo el cambio de nombre**, tras haber restaurado la etapa `restored` en TVH. La acción precisa de "reiniciar PVR" (reiniciar cliente HTSP, servicio PVR o alternar estado del complemento) **no se ha especificado todavía**, y no debe equipararse a un reinicio completo de Kodi.

Evidencia declarada: `G3AB_RESTORED_KODI_LABEL_AFTER_PVR_RESTART=UPDATED_OPERATOR_REPORTED`. **No se han vuelto a imprimir** los `channelid` después de esta acción, por lo que `G3AB_RESTORED_KODI_ID_STABLE_AFTER_PVR_RESTART=NOT_YET_VERIFIED`. El nombre de TVH había vuelto al original con los UUID esperados.

Implicación: reiniciar la capa PVR refrescó el nombre sin reiniciar Kodi entero, opción potencialmente preferible a reinicio total, pero **no autoriza** recomendar ciclos de desactivación/activación masivos, ni constituye solución validada para uso periódico o durante reproducción. Investigar mecanismo mínimo de actualización y si emite los eventos HTSP necesarios. Antes de pasar a `url`, verificar Kodi Alpha=`G3AB Alpha` ID=2 y Beta=`G3AB Beta` ID=1. `G3AB_URL_STAGE=PENDING_RESTORED_ID_CONFIRMATION`. No borrar SQLite.


## G3-AB restored: Kodi recupera nombres y conserva IDs tras reinicio PVR (2026-11-21)

Después de que el operador reiniciara PVR dentro de Kodi (acción concreta todavía sin especificar), ejecutó `PVR.GetChannels` y obtuvo:

```text
ID: 2 NOMBRE: G3AB Alpha
ID: 1 NOMBRE: G3AB Beta
```

Previamente TVH había recuperado los nombres originales y seguía mostrando 2 canales con sus UUID iniciales. Se valida `G3AB_RESTORED_TVH=PASS`, `G3AB_RESTORED_KODI=PASS`, `G3AB_RESTORED_KODI_IDS_STABLE=PASS`, `G3AB_RENAME_AND_RESTORE_NATIVE_IDENTITIES=PASS_OBSERVED`, `G3AB_CUID_CAUSALITY=UNPROVEN`, `G3AB_LIVE_LABEL_REFRESH=FAIL_OBSERVED`. **No** inferir que esta técnica es segura durante reproducción real ni emplearla automáticamente en master.

Siguiente gate `url`: partiendo de la M3U restaurada, escribir solo el cambio de URL sintética de Alpha a `http://streams/ch1-alt.ts`; capturar inventarios TVH/Kodi y multiplexor/servicio previos y posteriores (sin exponer URLs reales). La etapa puede desencadenar reasignación de mux o servicio aun manteniendo CUID; comprobar la convergencia antes de asumir fallo o éxito. No borrar entradas TVH ni SQLite; no modificar CoreELEC.


## Prioridad de arquitectura: actualización del cliente PVR en caliente (2026-11-21)

El operador fija como objetivo principal: **que el cliente PVR refresque** sin tocar SQLite ni reconstruir la biblioteca. Evidencia del laboratorio: TVH actualiza renombrado/restauración, Kodi mantiene `channelid` pero su `label` no converge mientras permanece conectado; un reinicio manual de PVR consigue actualizar la etiqueta con ID estable. Evitar confundir problema de notificación de metadatos con identidad o con baja de huérfanos.

Hipótesis a contrastar secuencialmente (sin cambios destructivos): (a) ¿TVH emite `channelUpdate` HTSP con `channelName`? (b) ¿`pvr.hts` recibe el mensaje? (c) ¿invoca la señal de actualización de canales de la API del addon Kodi? (d) ¿Kodi actualiza el `label` asociado al mismo `channelid`? Consultar código de `kodi-pvr/pvr.hts` en rama/versión compatible con CoreELEC 21.2.6.1, no asumir que Piers 22 tiene el mismo comportamiento.

Fuentes consultadas: Kodi builtin list https://kodi.wiki/view/List_of_built-in_functions y JSON-RPC API https://kodi.wiki/view/JSON-RPC_API/v12. **No se ha identificado un JSON-RPC público documentado `PVR.UpdateChannels`**; `PVR.Scan` no es un refresco genérico de metadatos, sino búsqueda/scan. No prometer comandos no comprobados.

Criterio de éxito futuro: actualización sin reiniciar Kodi, sin toggles deshabilitar/habilitar el addon, sin escrituras SQLite, sin afectar reproducción activa, conservando UUID TVH, Kodi IDs, grupos y preferencias; fallback de reinicio del cliente solo tras validación y fuera de reproducción. `G3AB_HOT_REFRESH_IMPLEMENTED=NO`, `G3AB_HTSP_NOTIFICATION_DIAGNOSIS=PENDING`, `MASTER_TOUCHED=NO`.


## Snapshot posterior: UUID TVH de canal, servicio y mux sin cambios; URL sin acreditar

El operador comunicó un snapshot de solo lectura:

```text
CANAL: G3AB Alpha
UUID: 185e5bdda6aafa6aa1aad2bb94ee703a
SERVICIO_UUID: 18cd0031a734c2342ac3956d754fb63e
MUX_UUID: 4d3f4f0b654e570dc39029bebaf5c555
CANAL: G3AB Beta
UUID: f08f75aa26b58386630d4b225adbb34f
SERVICIO_UUID: afe6f317e9b95eb03f6d91691e80f537
MUX_UUID: 355a43f5f4c718478b87d3b6a1bc8408
CANALES: 2
SERVICIOS: 3
MUXES: 2
```

Estos son los UUID ya observados en el baseline anterior al ensayo de URL. Por tanto `G3AB_TVH_CHANNEL_UUID_STABLE=YES_OBSERVED`, `G3AB_TVH_SERVICE_UUID_STABLE=YES_OBSERVED`, `G3AB_TVH_MUX_UUID_STABLE=YES_OBSERVED`, **pero** `G3AB_URL_FILE_CHANGED=NOT_REPORTED` y `G3AB_URL_APPLIED_TO_MUX=UNPROVEN`: la salida no incluye confirmación de `prepare.py url` ni comprobación del campo URL del mux. No inferir que TVH conserva los muxes ante un cambio de URL real hasta probar que se aplicó. Prioridad de arquitectura sigue en refresco nativo cliente PVR; no tocar SQLite, no eliminar servicios ni ejecutar en master.


## G3-AB URL: nueva URL verificada en M3U, URL efectiva de TVH pendiente

El operador ejecutó una lectura de `runtime/playlist/playlist.m3u` con el siguiente resultado:

```text
URL_ALTERNATIVA_EN_M3U: True
URL_ORIGINAL_ALPHA_EN_M3U: False
```

Esto acredita que la M3U activa del laboratorio G3-AB contiene `http://streams/ch1-alt.ts` y **no** la URL base de Alpha `http://streams/ch1.ts`. El snapshot previo de TVH mantuvo UUID de canal/servicio/mux y recuentos 2/3/2, pero **no leyó el atributo URL efectivo del mux** y no determina si el refresco de TVH aplicó el cambio. Estado: `G3AB_URL_FILE_CHANGED=YES`; `G3AB_URL_TVH_APPLIED=NOT_YET_VERIFIED`; `G3AB_URL_TVH_UUID_STABLE=OBSERVED_SNAPSHOT_ONLY`; `G3AB_KODI_URL_PLAYBACK=NOT_TESTED`; `G3AB_CUID_CAUSALITY=UNPROVEN`.

Siguiente gate: consultar `mpegts/mux/grid` con GET para el mux UUID Alpha y comprobar, sin imprimir URL, si los atributos de URL apuntan a `ch1-alt.ts` (y no `ch1.ts`). No inventar nombres de campos: enumerar únicamente nombres de campos relacionados con URL antes de extraer su valor. No reiniciar TVH/Kodi, no modificar SQLite, no tocar master. Si no está el campo en `grid`, consultar por GET el detalle read-only de `idnode/load` o marcar como no probado.


## G3-AB URL: UUID original del mux Alpha ausente en consulta posterior

El operador ejecutó `GET mpegts/mux/grid?start=0&limit=100` buscando el UUID de mux Alpha previo `4d3f4f0b654e570dc39029bebaf5c555` y reportó:

```text
MUX_ALPHA_EXISTE: False
```

La M3U de laboratorio tenía previamente confirmada la URL alternativa de Alpha, y el snapshot de TVH obtenido en otro instante todavía mostraba UUID de canal/servicio/mux originales. **Cambio temporal entre snapshots:** el mux anterior ya no figura en el último `mux/grid`, lo que es compatible con sustitución del mux al cambiar URL, pero NO basta para afirmar creación de otro mux ni funcionamiento del flujo o estabilidad actual de canal y servicio. `G3AB_ORIGINAL_ALPHA_MUX_PRESENT=NO_CURRENT_SNAPSHOT`; `G3AB_URL_EFFECTIVE=NOT_PROVEN`; `G3AB_CHANNEL_UUID_STABLE_AFTER_MUX_CHANGE=NOT_RECHECKED`; `G3AB_KODI_CHANNELID_STABLE_AFTER_URL=NOT_RECHECKED`.

Siguiente gate: consulta GET única de `channel/grid`, `mpegts/service/grid`, `mpegts/mux/grid`; imprimir solo UUID/relaciones **sintéticas G3-AB** y banderas de URL comparadas con `http://streams/ch1-alt.ts` sin mostrar valores de URI. No tocar master, no ejecutar limpiezas de servicios, ni reiniciar TVH para 'arreglar' la prueba. Confrontar cambios del objeto mux y del mapeo de canal antes de especular sobre regeneración o éxito de CUID.


## G3-AB URL: UUID original de Alpha ausente tras cambiar URL (operador, 2026-11-21)

El operador ejecutó lectura GET conjunta de canales, servicios y muxes en el TVH G3-AB cuando la M3U ya contenía `ch1-alt.ts`:

```text
CANALES: 2
SERVICIOS: 3
MUXES: 2
=== G3AB Alpha ===
UUID_CANAL_CONSERVADO: False
=== G3AB Beta ===
UUID_CANAL_CONSERVADO: True
NOMBRE_ACTUAL: G3AB Beta
SERVICIO_UUID: afe6f317e9b95eb03f6d91691e80f537
MUX_UUID: 355a43f5f4c718478b87d3b6a1bc8408
MUX_EN_INVENTARIO: True
SERVICIO_HABILITADO: True
CAMPOS_URL: ['iptv_url', 'iptv_url_cmpid']
URL_ALTERNATIVA_EN_MUX: False
```

**Gate crítico:** Alpha ya no aparece bajo su UUID de canal original `185e5bdda6aafa6aa1aad2bb94ee703a` en este snapshot, mientras Beta conserva `f08f75aa26b58386630d4b225adbb34f`. Es compatible con sustitución/recreación de Alpha desencadenada por URL, pero aún no se ha identificado el UUID del segundo canal actual ni verificado en él que `iptv_url` sea exactamente `http://streams/ch1-alt.ts`. Tampoco se ha consultado Kodi tras el cambio; `channelid` puede permanecer, cambiar o quedar obsoleto. La estabilidad de CUID en la M3U **no garantiza UUID TVH estable en este ensayo**; no atribuir uso de CUID a TVH.

`G3AB_URL_ALPHA_OLD_TVH_UUID_PRESENT=NO`
`G3AB_URL_BETA_OLD_TVH_UUID_PRESENT=YES`
`G3AB_URL_ALPHA_NEW_TVH_UUID=NOT_RECORDED`
`G3AB_URL_ALPHA_EFFECTIVE_MUX_URL=NOT_YET_VERIFIED`
`G3AB_URL_KODI_CHANNELID=NOT_YET_VERIFIED`
`G3AB_CUTOVER_AUTHORIZED=NO`

**No reiniciar PVR todavía**, ni modificar playlist, ni eliminar canales, servicios o muxes. Siguiente diagnóstico read-only: inventariar los 2 canales actuales (nombres, UUID, refs de servicio, mux), comprobar `iptv_url` en mux Alpha y obtener simultáneamente `PVR.GetChannels` de Kodi. Si cambia identidad en Kodi, priorizar la reconciliación no destructiva y plan para pérdida de identidad; reinicio PVR solo ensayo posterior con snapshot previo.


## G3-AB URL: sustitución confirmada de canal, servicio y mux Alpha; Kodi ID aparente sin prueba de convergencia

Operador ejecutó lectura combinada TVH `channel/grid`, `mpegts/service/grid`, `mpegts/mux/grid` y Kodi `PVR.GetChannels`, **sin reiniciar PVR antes**:

```text
=== TVHEADEND ===
CANAL: G3AB Alpha
UUID: 780608ad2385d70c9d46279e0f62250e
UUID_ORIGINAL_ALPHA: False
SERVICIO: 5a6962a3ab51cfec0c933f6cc7eda030
MUX: f9e55f38b435969d396393edc3b7acc4
URL_ALTERNATIVA: True
---
CANAL: G3AB Beta
UUID: f08f75aa26b58386630d4b225adbb34f
UUID_ORIGINAL_ALPHA: False
SERVICIO: afe6f317e9b95eb03f6d91691e80f537
MUX: 355a43f5f4c718478b87d3b6a1bc8408
URL_ALTERNATIVA: False
---
=== KODI ===
ID: 2 NOMBRE: G3AB Alpha
ID: 1 NOMBRE: G3AB Beta
TVH_TOTAL: 2
KODI_TOTAL: 2
```

**Evidencia fuerte:** el Alpha actualmente activo en TVH usa URL alternativa real y UUID nuevos para canal, servicio y mux; el Alpha anterior usaba canal `185e5bdda6aafa6aa1aad2bb94ee703a`, servicio `18cd0031a734c2342ac3956d754fb63e`, mux `4d3f4f0b654e570dc39029bebaf5c555`. El Beta conserva canal `f08f75aa26b58386630d4b225adbb34f`, servicio `afe6f317e9b95eb03f6d91691e80f537`, mux `355a43f5f4c718478b87d3b6a1bc8408`.

`G3AB_URL_TVH_APPLIED=YES`, `G3AB_URL_ALPHA_CHANNEL_UUID_REPLACED=YES`, `G3AB_URL_ALPHA_SERVICE_UUID_REPLACED=YES`, `G3AB_URL_ALPHA_MUX_UUID_REPLACED=YES`, `G3AB_URL_BETA_STABLE=YES`, `G3AB_KODI_ALPHA_CHANNELID_CURRENT=2`, pero **`G3AB_KODI_NEW_BACKEND_CHANNEL_ACCEPTED=UNPROVEN`**: mostrar ID 2 y nombre Alpha sin verificar la correspondencia backend puede ser estado previo/caché. `CUID` estable en M3U no evitó recreación en TVH. No afirmar persistencia Kodi ni corrección nativa ante cambios URL hasta reconexión PVR y captura posterior.

Siguiente prueba aislada, controlada por operador: observar estado Kodi PVR tras un refresco manual del cliente que anteriormente funcionó (mecanismo exacto aún no documentado). Registrar ambos channelid, nombres y número total. No borrar DB ni activar borrados, no tocar producción, y no declarar reparación si no se comprueba que Kodi tiene el nuevo canal backend; idealmente contrastar el identificador HTSP con el UUID TVH mediante diagnóstico del cliente en un gate aparte.


## G3-AB URL: Kodi conserva channelid tras refresco manual PVR, backend sin verificar (2026-11-21)

Después de la lectura previa al refresco, el operador realizó la acción solicitada de actualización/reinicio PVR y consultó `PVR.GetChannels`:

```text
ID: 2 NOMBRE: G3AB Alpha
ID: 1 NOMBRE: G3AB Beta
TOTAL: 2
```

**Observación:** tras el refresco manual no hay duplicados visibles y Kodi mantiene ambos `channelid` originales, a pesar de que TVH ya había sustituido canal, servicio y mux de Alpha al cambiar la URL. `G3AB_URL_KODI_AFTER_PVR_REFRESH_COUNT=2`, `G3AB_URL_KODI_AFTER_PVR_REFRESH_ALPHA_ID=2`, `G3AB_URL_KODI_AFTER_PVR_REFRESH_BETA_ID=1`. Esto **no demuestra aún** que el Kodi Alpha resuelva al nuevo backend TVH ni reproduzca desde `http://streams/ch1-alt.ts`; tampoco demuestra que CUID mantenga la identidad (TVH sustituyó el UUID).

**Nuevo gate:** abrir Alpha G3-AB desde GUI Kodi de laboratorio, comprobar la reproducción audiovisual y observar por GET `/api/status/subscriptions` del TVH G3-AB durante la sesión para relacionar servicio/mux nuevo con el canal reproducido. Si el status no incluye identificador explícito de servicio, limitar la conclusión a observación audiovisual y no inferir un vínculo UUID. Evitar invocar un comando de reproducción JSON-RPC sin prueba de disponibilidad y no alterar TVxx.db ni servicios. Cuidar duración del TS sintético (12 s) y errores EPG/imagecache ajenos. No emplear en master.


## G3-AB URL: suscripción Kodi→TVH Alpha observada, service UUID no aparece (2026-11-21)

El operador reprodujo `G3AB Alpha` desde el Kodi G3-AB y consultó `GET /api/status/subscriptions`:

```text
SUSCRIPCIONES_ACTIVAS: 1
CAMPOS_DISPONIBLES: ['channel', 'client', 'errors', 'hostname', 'id', 'in', 'out', 'pids', 'profile', 'service', 'start', 'state', 'title', 'total_in', 'total_out', 'username']
CANAL: G3AB Alpha
SERVICIO_UUID_NUEVO_PRESENTE: False
```

**Interpretación estricta:** TVH informó una suscripción activa nominalmente para Alpha. La búsqueda de cadena UUID nuevo `5a6962a3ab51cfec0c933f6cc7eda030` dentro de `str(entry)` fue falsa, pero eso **no demuestra uso del servicio antiguo**: la propiedad `service` puede ser etiqueta textual en lugar de UUID. Tampoco se observaron valores de transferencia `in/out/total_in/total_out`, `state` o `errors`, por lo que reproducción de datos aún no acreditada. El TS sintético tiene 12 s, por lo que la ventana de medición es corta.

`G3AB_URL_KODI_TVH_SUBSCRIPTION=OBSERVED_1`; `G3AB_URL_STATUS_CHANNEL=ALPHA`; `G3AB_URL_SERVICE_UUID_MATCH=NOT_AVAILABLE_FROM_CURRENT_FIELDS`; `G3AB_URL_STREAM_BYTES=NOT_YET_CHECKED`; `G3AB_URL_KODI_PLAYBACK=NOT_YET_VERIFIED`. Próximo diagnóstico de solo lectura: observar campo `service` como tipo/igualdad con nombre de servicio sintético y contadores de bytes/estado/errores, sin credenciales ni IPs. No sacar conclusión causal por ausencia de UUID en estado.


## G3-AB URL: TVH registra reproducción de Alpha con tráfico y cero errores (2026-11-21)

El operador consultó `GET /api/status/subscriptions` durante la reproducción de G3AB Alpha:

```text
CANAL: G3AB Alpha
TIPO_SERVICIO: str
SERVICIO: IPTV #1/IPTV LOCAL/playlist.m3u - G3AB Alpha/G3AB Signal 1
ESTADO: Running
ERRORES: 0
ENTRADA: 128404
SALIDA: 115971
TOTAL_ENTRADA: 965192
TOTAL_SALIDA: 881587
```

El estado de suscripción `Running`, el contador de errores `0` y contadores no nulos de tráfico acreditan flujo servido desde TVH al cliente mientras la suscripción está activa. La propiedad `service` es una descripción `str`, no contiene UUID; por tanto este endpoint **no prueba directamente** igualdad con UUID del nuevo servicio. La relación de inventario del canal Alpha con nuevo servicio/mux y URL alternativa **sí** se verificó previamente por API GET. La salida no acredita aún que el usuario haya observado vídeo y audio en pantalla Kodi.

`G3AB_URL_ALPHA_TVH_SUBSCRIPTION_RUNNING=PASS`; `G3AB_URL_ALPHA_TVH_SUBSCRIPTION_ERRORS=0`; `G3AB_URL_ALPHA_TVH_STREAM_BYTES=OBSERVED_NONZERO`; `G3AB_URL_KODI_CHANNELID_AFTER_REFRESH=2`; `G3AB_URL_AV_PLAYBACK_ON_SCREEN=UNCONFIRMED`. Conclusión: evidencia sólida de entrega del TS de laboratorio tras actualización de URL, sin atribución causal al atributo CUID, y con regeneración de UUIDs TVH. Próxima prioridad: investigar mecanismo de refresco en caliente de `pvr.hts` y eventos HTSP, conservar PVR/Kodi IDs, no modificar SQLite ni master; documentar reproducción audiovisual si operador la confirma.
