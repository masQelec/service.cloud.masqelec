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
