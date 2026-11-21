# G3-W — laboratorio TVH aislado para ensayo real 2→3→2

Fecha 2026-11-21; rama `develop`. **Preparado, NO ejecutado en equipos del operador.**

## Por qué y qué se aísla

La M3U de producción tiene 720 canales, TVH 720 y Kodi 720 (coincidencia descriptiva; 24 entradas con nombres duplicados). No se ha demostrado la baja nativa en Kodi. El validador offline G3-V (10/10 tests confirmados) no reemplaza la observación de un servidor real.

Este bloque prepara un laboratorio separado en Ubuntu:
- Compose `masqelec-pvr-g3w`, imagen `lscr.io/linuxserver/tvheadend:latest` con **configuración nueva en runtime/tvh_config**. Solo puertos loopback **127.0.0.1:19981** (web) y **127.0.0.1:19982** (HTSP), NO 9981/9982 de producción. Imagen y ajustes siguiendo documentación de LinuxServer: https://docs.linuxserver.io/images/docker-tvheadend/
- Nginx sirve archivos MPEGTS sintéticos dentro de la red Docker. No se publica ningún puerto de Nginx al host. La red de Compose emplea bridge estándar; no usar `internal: true` porque impide acceder a la web desde el host en esta instalación. Los únicos puertos publicados de TVH están enlazados a 127.0.0.1.
- `prepare.py before|added|removed` instala playlist **solo** en `lab/pvr_g3w/runtime/playlist/playlist.m3u`. La M3U generada referencia `http://streams/ch1.ts`, `ch2.ts`, `ch3.ts` en la red privada, con 2→3→2 entradas y nombres `G3W Synthetic N`. Flujos de 12 segundos generados mediante ffmpeg local; sirven para descubrimiento de servicios y pruebas, **no** para reproducción sostenida ni medición de calidad.
- `runtime/` ignorado por Git. Sin credenciales IPTV reales. No usar puertos del master.
- El contenedor no recibe montajes de `/storage/.user`, `/storage/.kodi` ni configuración existente de Tvheadend.

**Limitación técnica:** la imagen de LinuxServer documenta que algunas configuraciones IPTV multicast requieren `network_mode: host`. Este experimento usa **HTTP unicast a través de la red privada de Compose** para evitar ese requisito; no presupone que todos los métodos IPTV funcionen en bridge. La configuración manual de TVH y el mapeo efectivo de canales deben verificarse, no darse por hechos.

## Preparación y pruebas en Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3w_lab_fixture.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3v_isolated_delta_gate.py' -v

cd service.cloud.masqelec/lab/pvr_g3w
command -v docker
docker compose config --quiet
python3 prepare.py before
docker compose up -d
docker compose ps
```

Esperados **20 tests** (10 G3-W + 10 G3-V); no afirmar PASS antes de salida real.

**Si ffmpeg no está instalado:** instalarlo en la máquina **Ubuntu de laboratorio**, no en el master. No iniciar contenedores en CoreELEC.

## Configurar TVH y Kodi de laboratorio — sin reutilizar cuentas ni bases de producción

1. En el navegador de Ubuntu, abrir `http://127.0.0.1:19981` y terminar el asistente inicial de Tvheadend. Crear la red IPTV **Automatic IPTV Network** apuntando a `file:///lab_playlist/playlist.m3u`, con intervalo de refetch corto solo para laboratorio. Habilitar descubrimiento, mapear servicios y, si se utiliza bouquet, generar canales/grupos correspondientes. Comprobar explícitamente que TVH ve **2 canales válidos** antes de continuar.
2. Ejecutar una instancia **separada** de Kodi con perfil aislado (VM, contenedor con GUI o segundo dispositivo de laboratorio), sin reutilizar `/storage/.kodi/userdata`. Conectar **solo** `pvr.hts` al servidor de laboratorio por puerto HTSP **19982**. La dirección será la IP/hostname de Ubuntu si el Kodi de laboratorio es externo; como los puertos están ligados a 127.0.0.1, acceder desde otra máquina requiere un túnel SSH explícito o ejecutar Kodi en el mismo host. No abrir el servicio a toda la LAN por comodidad.
3. Mediante `PVR.GetChannels(channelgroupid="alltv")` en **el Kodi aislado**, comprobar que hay **2 canales**. Registrar IDs y nombres del canal del laboratorio (no de producción).
4. Capturar estado `before` y evidencia independiente del refetch TVH; guardar evidencias **solo en directorio privado de laboratorio**, nunca en Git.
5. Ejecutar `python3 prepare.py added` en Ubuntu. La M3U del contenedor pasará a 3 entradas. Esperar/revisar una relectura TVH verificable por logs o eventos de servicios. Comprobar TVH 3, Kodi aislado 3 y IDs conservados de los 2 originales.
6. Ejecutar `python3 prepare.py removed`. Confirmar TVH 2 y Kodi 2, que el tercero desaparece de ambos y los dos IDs originales se conservan. **Si Kodi mantiene el tercero, ese es el fallo a resolver**: no forzar una limpieza SQLite para hacer que el ensayo pase.
7. Redactar el informe JSON de G3-V con los IDs y nombres observados en cada etapa y evidencias de procedencia auténticas. Ejecutar el validador offline `tools/pvr_g3v_isolated_delta_gate.py` y documentar salida real.
8. Al acabar, desde la carpeta de laboratorio: `docker compose down`. **No** utilizar `down -v` ni borrar archivos de configuración sin revisar lo recogido.

## Gates: no alterar el master

- Nunca usar `/storage/.user/playlist.m3u` ni los puertos 9981/9982 del master.
- No conectar el Kodi de uso familiar a este servidor de pruebas.
- No compartir credenciales, URL IPTV ni respuestas JSON-RPC con información privada.
- **Una coincidencia inicial 2/2 no demuestra baja.** Se requiere observar 2→3→2 con evidencia de relectura y estabilidad de IDs; si TVH vuelve a 2 pero Kodi permanece en 3, `NATIVE_ORPHAN_REMOVAL=FAIL`.
- Si la instalación necesita modificar el equipo de producción, `G3W=DEFERRED` y no se ejecuta.

## Estado y decisión

`G3W_FIXTURE_PREPARED=YES`
`G3W_LOCAL_UNIT_TESTS=PENDING`
`G3W_DOCKER_LAB_STARTED=NO`
`G3W_REAL_TVH_DELTA=NOT_TESTED`
`G3W_REAL_KODI_DELTA=NOT_TESTED`
`LEGACY_SQLITE_FALLBACK_REMOVED=NO`
`PRODUCTION_MODIFIED=NO`

La eliminación del mantenimiento heredado no está autorizada por este scaffold: depende del ensayo funcional, la auditoría de SQLite activa y la estrategia de recuperación.


## Incidencia real: publicación de puertos Docker (2026-11-21)

El operador ha creado la M3U de 2 canales y arrancado ambos contenedores, pero informó `docker compose port tvh 9981=:0`, `9982=:0` y `curl http://127.0.0.1:19981` con conexión rehusada. Los logs muestran TVH iniciado y escuchando en 9981 **dentro del contenedor**. `docker compose config` sí reflejaba `127.0.0.1:19981→9981` y `127.0.0.1:19982→9982`. Recrear solo TVH no cambió el resultado.

Se ha cambiado exclusivamente la red de laboratorio de `internal: true` a `driver: bridge` (estándar). Según la documentación de Docker, `internal` crea una red sin conexión a interfaces del host, mientras que bridge estándar permite publicar puertos con NAT. Fuentes: https://docs.docker.com/compose/how-tos/networking/ y https://docs.docker.com/engine/network/port-publishing/.

Para que Docker aplique el cambio de tipo de red **hay que recrear la red del proyecto**, no solo el contenedor TVH:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
cd service.cloud.masqelec/lab/pvr_g3w
docker compose config --quiet
docker compose down
docker compose up -d
docker compose ps
docker compose port tvh 9981
curl -sS -o /dev/null -w 'HTTP=%{http_code}\n' --max-time 10 http://127.0.0.1:19981/
```

`docker compose down` sin `-v` no borra los datos del laboratorio en `runtime/`. Sigue sin tocar TVH/CoreELEC reales. Si la publicación continúa fallando, revisar `docker inspect masqelec-pvr-g3w-tvh-1 --format '{{json .HostConfig.PortBindings}} {{json .NetworkSettings.Ports}}'` y configuración del daemon antes de cambiar otras opciones. **Este parche no ha sido aún validado por el operador**. No abrir puertos a `0.0.0.0` ni usar `network_mode: host` como solución rápida.


## Evidencia real de arranque del laboratorio (captura 2026-11-21 10:41:52 CET)

El operador confirmó **web funcional y M3U configurada** y aportó una captura HTML SingleFile de `http://127.0.0.1:19981/extjs.html`, vista Configuración → Canal / EPG → Canales. La inspección de las dos filas visibles muestra:
- `G3W Synthetic 1`, número 1, habilitado, con servicio IPTV asociado, categoría `G3W TEST`.
- `G3W Synthetic 2`, número 2, habilitado, con servicio IPTV asociado, categoría `G3W TEST`.
- Paginador: **Canales 1–2 de 2**. El canal 3 no aparece.
- Captura del LAB, no del master. La vista indica «Acceso no verificado»; mantener la publicación HTTP en `127.0.0.1`, no abrir la interfaz a toda la red sin control de acceso.

**`G3W_TVH_INITIAL_TWO_CHANNELS=PASS_VISUAL`**. Esto demuestra ingestión y mapeo inicial de dos canales en TVH de laboratorio; aún NO demuestra relectura automática, 2→3→2, ni cambio real en Kodi.

**Siguiente paso obligatorio:** conectar un Kodi con perfil separado al HTSP del TVH de laboratorio (host Ubuntu, puerto localhost 19982 o túnel SSH controlado), registrar sus dos canales iniciales y sus IDs. No cambiar a etapa `added` antes de completar esa línea base. La suite G3-W no se declara confirmada numéricamente solo porque la salida presentada por el operador incluyera «OK», sin cabecera de número de tests.

**Estado:** `G3W_WEB_PORTS=WORKING`, `G3W_TVH_INITIAL_TWO_CHANNELS=PASS_VISUAL`, `G3W_KODI_LAB_BASELINE=PENDING`, `G3W_REAL_DELTA=PENDING`, `PRODUCTION_UNTOUCHED=YES`.


## Baseline visual Kodi aislado — 2026-11-21 10:48 CET

El operador aporta captura de **TV → Canales → Todos los canales** en Kodi de Ubuntu, mostrando exclusivamente `G3W Synthetic 1` (número 1) y `G3W Synthetic 2` (número 2), indicador `1 / 2`. TVH de laboratorio ya había mostrado 2/2.

`G3W_KODI_LAB_BASELINE_VISUAL=PASS_2_OF_2`. Todavía **no** constan IDs internos Kodi `channelid` ni UUID de TVH, ni se ha observado alta/baja. Registrar IDs por APIs de solo lectura antes de ejecutar `prepare.py added`, para validar identidad persistente. Kodi JSON-RPC HTTP local debe habilitarse solo en perfil Ubuntu de laboratorio, sin exponerlo a la LAN.


## Baseline Kodi JSON-RPC real — 2026-11-21

El operador ha habilitado JSON-RPC en el Kodi de Ubuntu de laboratorio y ejecutado correctamente `PVR.GetChannels` con `channelgroupid=alltv`. Respuesta real:

```json
{"channels":[{"channelid":1,"label":"G3W Synthetic 1"},{"channelid":2,"label":"G3W Synthetic 2"}],"limits":{"end":2,"start":0,"total":2}}
```

`G3W_KODI_BASELINE_NATIVE=PASS_2_OF_2`. Identificadores Kodi que **deben persistir**: Synthetic 1 → `channelid=1`; Synthetic 2 → `channelid=2`. `G3W_TVH_UUID_BASELINE=PENDING`; obtener UUID de TVH con `/api/channel/grid` antes del alta. No afirmar que Kodi borrará el tercer canal hasta observar la baja real. Los IDs de Kodi son enteros y el gate G3-V usa cadenas; convertirlos explícitamente al generar el informe de validación.


## Alta preparada, pendiente de propagación real

Operador aporta línea base TVH GET `channel/grid`:

```text
UUID: 01acdb29035f6789d905cfd14f8ef5b0 NOMBRE: G3W Synthetic 1
UUID: 918d272bf55884716e5fff5177ee8b08 NOMBRE: G3W Synthetic 2
TOTAL: 2
```

Posteriormente ejecutó el generador de etapa `added`, que informa:

```text
G3W_STAGE=ADDED
G3W_CHANNELS=3
G3W_PLAYLIST_ONLY_IN_LAB=YES
G3W_MASTER_UNTOUCHED=YES
```

Interpretación precisa: **playlist de laboratorio escrita con tres entradas**, todavía **NO** comprobado que TVH haya hecho refetch ni que Kodi haya recibido canal 3. Solicitar ambos snapshots de sólo lectura. No pasar a `removed` hasta registrar TVH 3/Kodi 3 y estabilidad de UUID/IDs originales.


## Alta real 2→3 confirmada (operador, 2026-11-21)

Salida de observación real de TVH (API GET) y Kodi (JSON-RPC de lectura) tras `python3 prepare.py added`:

```text
=== TVHEADEND ===
UUID: 01acdb29035f6789d905cfd14f8ef5b0 NOMBRE: G3W Synthetic 1
UUID: 918d272bf55884716e5fff5177ee8b08 NOMBRE: G3W Synthetic 2
UUID: 29639cb6a761cc5523a10aae45c45404 NOMBRE: G3W Synthetic 3
TOTAL: 3
=== KODI ===
ID: 1 NOMBRE: G3W Synthetic 1
ID: 2 NOMBRE: G3W Synthetic 2
ID: 3 NOMBRE: G3W Synthetic 3
TOTAL: 3
```

`G3W_TVH_ADD=PASS_3_OF_3`; `G3W_KODI_ADD=PASS_3_OF_3`; `G3W_RETAINED_IDS_STABLE_DURING_ADD=YES`. Esto comprueba recepción del nuevo canal sin reinicio solicitado; el suceso exacto de refetch y el borrado automático de huérfanos **no** están aún acreditados. El siguiente paso es cambiar **solo** la M3U sintética de laboratorio con `prepare.py removed` y consultar TVH/Kodi por interfaces de solo lectura. No tocar master, PVR real ni SQLite.


## Baja real 3→2 y ciclo completo 2→3→2 — confirmados por operador

Tras ejecutar únicamente el generador de fixture `python3 prepare.py removed`:

```text
G3W_STAGE=REMOVED
G3W_CHANNELS=2
G3W_PLAYLIST_ONLY_IN_LAB=YES
G3W_MASTER_UNTOUCHED=YES
=== TVHEADEND ===
UUID: 01acdb29035f6789d905cfd14f8ef5b0 NOMBRE: G3W Synthetic 1
UUID: 918d272bf55884716e5fff5177ee8b08 NOMBRE: G3W Synthetic 2
TOTAL: 2
=== KODI ===
ID: 1 NOMBRE: G3W Synthetic 1
ID: 2 NOMBRE: G3W Synthetic 2
TOTAL: 2
```

Se completa el ciclo de inventarios observado **TVH 2→3→2, Kodi 2→3→2**, manteniendo los UUID TVH `01acdb29035f6789d905cfd14f8ef5b0` y `918d272bf55884716e5fff5177ee8b08` y los IDs Kodi 1 y 2. Durante este ensayo no se solicitó reiniciar TVH/Kodi ni acceder a SQLite. Resultado: `G3W_TVH_REMOVE=PASS`, `G3W_KODI_REMOVE=PASS`, `G3W_NATIVE_ORPHAN_REMOVAL_OBSERVED=YES_ON_UBUNTU_LAB`.

**Alcance y cautelas:** la coincidencia por API de dos snapshots no acredita por sí sola fecha exacta del evento de refetch ni que el mismo comportamiento exista en la versión CoreELEC/pvr.hts del master. El gate G3-V aún exige una declaración verificable del evento de refetch y conexión exclusiva Kodi laboratorio→TVH laboratorio antes de producir `LAB_DELTA=PASS` en su validador offline. La ausencia de escritura SQL se deduce del procedimiento realizado, no de auditoría de todos los procesos en el equipo. No se activó el nuevo sistema ni se retiró fallback legacy en producción.

**Próximo paso:** comparar versiones Kodi/pvr.hts en Ubuntu y CoreELEC; comprobar baja nativa en CoreELEC solo mediante piloto seguro y autorizado, sin eliminar canales de la M3U maestra. Solo tras eso decidir la refactorización de `update_pvr.py`, manteniendo rutas de recuperación y verificaciones de inventario.


## Comparación inicial de versiones — 2026-11-21

Evidencia directa del operador:

```text
UBUNTU
kodi 2:21.3+dfsg-1ubuntu1
kodi-pvr-hts 21.2.6+ds-1.1

CORELEC
VERSION="21.2.5-Omega_devel_20250919152246"
VERSION_ID="21.2.5"
LIBREELEC_ARCH="Amlogic-ng.arm"
LIBREELEC_BUILD="community"
LIBREELEC_PROJECT="Amlogic-ce"
```

No apareció línea `<version>` de addon.xml en las dos rutas inicialmente inspeccionadas del master: **la versión `pvr.hts` CoreELEC sigue desconocida**. Kodi Ubuntu 21.3 y CoreELEC 21.2.5 son cercanos pero no idénticos. `G3W_VERSION_EQUIVALENCE=NOT_PROVEN`; `G3W_CORELEC_NATIVE_REMOVE=NOT_TESTED`; no activar corte del mantenimiento legado por este parecido.

Para identificar la versión del addon sin alterar master, buscar en rutas Kodi propias del sistema (solo metadatos de addon.xml) o usar JSON-RPC `Addons.GetAddonDetails` en lectura. La clave SSH del operador solicitó passphrase tres veces; los resultados de `os-release` prueban conexión efectiva, no la ubicación de pvr.hts.
