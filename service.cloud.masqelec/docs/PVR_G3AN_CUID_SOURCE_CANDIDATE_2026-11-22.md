# G3-AN — CUID persistente IPTV: candidato restringido (22/11/2026)

## Motivación
G3-AM renombrado HTSP/Kodi PASS. Cambiar URL Alpha ch1.ts -> ch1.ts?g3am_url_test=1 manteniendo CUID g3am-001 reemplazó el UUID mux, servicio y canal TVH; Kodi iUniqueId cambió 1699146942 -> 354983035 aunque idChannel 2 y total 2 sobrevivieron.
Fuente Tvheadend exacta 8837853a6: iptv_auto.c empareja por mm_iptv_url_cmpid y elimina muxes anteriores no emparejados. misc/m3u.c sí conserva CUID dentro del htsmsg; no lo lee el importador. iptv_mux.c proporciona iptv_url_set para normalización de URL y tiene un campo de comparación separado.

## Implementación candidata — NO VALIDADA
tools/pvr_g3an_apply_cuid_lab.py aplica cambios de código fuente SOLO en un nuevo checkout /home/ubuntu/tvheadend-g3an-upstream, previamente parcheado con G3-AL. No opera sobre los ejecutables activos ni contenedores.
- Campo opcional mm_iptv_cuid en iptv_mux_t, propiedad PT_STR persistible pero oculta, liberada al destruir mux.
- Preflight playlist: CUID no vacío, ASCII restringido [A-Za-z0-9._-], máximo 128; rechazo de CUID repetidos y dos CUID diferentes con URL idéntica; rechazo de múltiples muxes que tengan mismo CUID; no actualizar URL mientras mm_active.
- Búsqueda por CUID antes de URL; se adopta por URL exclusivamente un mux antiguo sin CUID. No se adopta por nombre, número o posición.
- URL nueva en mux con CUID coincidente: usar setter iptv_url_set y actualizar mm_iptv_url_cmpid, persistiendo idnode_changed, sin reconstruir mux/servicio/canal.
- Se conserva la corrección G3-AL de notificación HTSP para nombres efectivos.

Limitaciones: sin compilación Ubuntu comprobada todavía. Playback activo aplaza el refetch completo, lo que puede retrasar otros cambios. Faltan gates de CUID duplicado/ausente, URLs compartidas, cambios host/path/query, reinicio TVH, reproducción, nueva playlist, Kodi PVR y compatibilidad CoreELEC. No desplegar en producción.

## Compilar en árbol separado, sin sustituir ejecutables activos
Desde Ubuntu, manteniendo G3-AM y Kodi tal como están:

    cd /home/ubuntu/GitHub/service.cloud.masqelec
    git pull --ff-only origin develop
    test ! -e /home/ubuntu/tvheadend-g3an-upstream
    git -C /home/ubuntu/tvheadend-g3al-upstream worktree add --detach /home/ubuntu/tvheadend-g3an-upstream 8837853a6
    cd /home/ubuntu/tvheadend-g3an-upstream
    git apply --check /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch
    git apply /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch
    python3 /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/tools/pvr_g3an_apply_cuid_lab.py /home/ubuntu/tvheadend-g3an-upstream
    python3 /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/tools/pvr_g3an_apply_cuid_lab.py /home/ubuntu/tvheadend-g3an-upstream --apply
    git diff --check
    git diff --stat

Tras los gates previos, sólo en este árbol ejecutar:

    ./configure --disable-ffmpeg_static --disable-libav --disable-doc
    make -j2
    test -x build.linux/tvheadend && echo G3AN_BUILD=PASS

PROHIBIDO: make install, sobrescribir /home/ubuntu/tvheadend-g3al-upstream/build.linux/tvheadend (montado por contenedor existente), reiniciar G3-AM sin autorización específica, cambiar G3-AB original, editar TV46.db. Después de build, diseñar un runtime G3-AN con configuración y Kodi separados. El UUID Alpha ya reemplazado en G3-AM no se recupera automáticamente; se partirá de nueva línea base adoptando URL existente y CUID antes de cambiarla.

## Estado
G3AM_RENAME_E2E=PASS
G3AM_URL_IDENTITY=FAIL_OBSERVED
G3AN_SOURCE_CANDIDATE=COMMITTED
G3AN_ANCHOR_CHECK_UBUNTU=PENDING
G3AN_BUILD_UBUNTU=PENDING
G3AN_ISOLATED_RUNTIME=PENDING
G3AN_NEGATIVE_CUID_TESTS=PENDING
G3AN_CORELEC_BUILD=NOT_AUTHORIZED

## Revisión de guardas antes del primer build

Se endureció el candidato para abortar, sin cambiar playlist ni muxes, si desaparece el CUID de una URL ya asociada a un mux identificado, o si la URL está asignada a un CUID distinto. También se sincroniza mm_iptv_url_cmpid incluso cuando el setter de URL decide que la forma normalizada de stream no ha variado. Ejecutar únicamente en nuevo worktree separado, nunca sobre binario G3-AL montado por Docker. Fuente candidata HEAD de herramienta en develop: commit 84252a70cd734620b31e87a7c0e3686c700b6df2.

**Auditoría pendiente de código:** el primer gate es `--dry-run` y `git diff --check`, no resultado de compatibilidad. La semántica de las rutas mixtas CUID/no-CUID, refetch abortado por reproducción activa, manejo de errores de memoria y regresión completa por CUID aún requiere pruebas; no se autoriza instalación. El build en Ubuntu y los ensayos de runtime deben confirmarse por evidencia del operador.

## Incidencia primer ensayo local — AUTO_CUID ancla no única (22/11/2026)

Usuario confirmó checkout separado existente en HEAD 8837853a, sólo `src/input/mpegts/iptv/iptv_auto.c` modificado (82 líneas añadidas, 2 eliminadas: G3-AL ya aplicado). G3-AM sigue vivo. `python3 -m py_compile` de transformador PASS; `--dry-run` falló `G3AN=BLOCKED_SOURCE_ANCHOR_MISMATCH_AUTO_CUID`, exit 2, por lo que **no se escribieron cambios G3-AN** ni se compiló. La causa del ancla es que el helper g3an_preflight, insertado durante el análisis en memoria, contiene otra sentencia idéntica `url = htsmsg_get_str(item, "m3u-url");`; la función replace_one requiere ocurrencia única. Ajustado el ancla a secuencia única que incluye `if (url == NULL ||`, commit `a19368ea3a6333f6edb647865442a7e88ac41a8b`. PENDIENTE que operador ejecute otra vez dry-run y se obtenga `G3AN_SOURCE_ANCHORS=PASS`; no afirmar compilación hasta ejecutarla. Nunca aplicar G3-AL de nuevo en el mismo worktree, no borrar ni resetear.

## Gate de transformación de fuentes superado en Ubuntu (22/11/2026)

Salida real comunicada por el operador tras corrección de ancla AUTO_CUID:

    G3AN_SOURCE_ANCHORS=PASS
    G3AN_APPLY=DRY_RUN
    G3AN_DRY_RUN_EXIT=0
    G3AN_SOURCE_ANCHORS=PASS
    G3AN_SOURCE_APPLIED=YES
    G3AN_APPLY_EXIT=0
    src/input/mpegts/iptv/iptv_auto.c    | 224 ++++++++++++++++++++++++++++++++++-
    src/input/mpegts/iptv/iptv_mux.c     |   8 ++
    src/input/mpegts/iptv/iptv_private.h |   1 +
    3 files changed, 229 insertions(+), 4 deletions(-)
    G3AN_SOURCE_RESULT=0

`git diff --check` devolvió 0 dentro del flujo. Esto sólo valida aplicación y formato: la compilación todavía no se ha ejecutado. Siguiente gate: configurar con `--disable-ffmpeg_static --disable-libav --disable-doc`, `make -j2` en **worktree G3-AN aislado**, guardando stdout/stderr en `/tmp/g3an-build.log`, sin `set -e` en la shell interactiva y sin sustituir ejecutable de G3-AM. Si falla mostrar líneas de error y log; no ejecutar `make install`. Confirmar G3AN_BUILD=PASS únicamente con salida del operador.

    G3AN_SOURCE_APPLY_UBUNTU=PASS
    G3AN_GIT_DIFF_CHECK=PASS
    G3AN_BUILD_UBUNTU=PENDING
    G3AN_RUNTIME_TEST=PENDING

## G3-AN primer configure fallido por dependencia dvbcsa (22/11/2026)

Operador informó `G3AN_BUILD_EXIT=1`, `G3AN_BUILD=FAIL` antes de make; configure marcó `checking for cc dvbcsa/dvbcsa.h ... fail`, `ERROR: Failed to find dvbcsa library`. No es evidencia de error en fuentes G3-AN. Inspección de `tvheadend/tvheadend@8837853a6/configure` líneas ~812-827 confirma que el chequeo dvbcsa se ejecuta dentro de `if enabled_or_auto tvhcsa`; la opción soportada `--disable-tvhcsa` evita ese requisito, sin instalar biblioteca extra para laboratorio IPTV sintético. Repetir configure + make exclusivamente en checkout G3-AN, flags `--disable-ffmpeg_static --disable-libav --disable-doc --disable-tvhcsa`, registrar /tmp/g3an-build.log y códigos por separado sin `set -e` en shell interactiva. Estado: `G3AN_SOURCE_APPLY=PASS`, `G3AN_FIRST_CONFIGURE=BLOCKED_MISSING_DVBCSA`, `G3AN_BUILD=PENDING_RETRY`; G3-AM no se reemplaza ni reinicia.

## G3-AN segundo build fallido en Makefile.webui (22/11/2026)

Operador: `G3AN_CONFIGURE_EXIT=0` con `--disable-tvhcsa`; `G3AN_MAKE_EXIT=2`, `G3AN_BUILD=FAIL`. Últimas líneas de log muestran `make[1]: *** [Makefile.webui:251: all] Error 2` y `make: *** [Makefile:854: make_webui] Error 2`; además `npm install` terminó con `added 369 packages... 28 vulnerabilities`, pero esos avisos NO explican automáticamente el fallo. `grep -nEi 'error:|undefined reference|fatal error|failed'` solo mostró `FAILED TO DOWNLOAD (BUT THIS IS NOT A FATAL ERROR! DO NOT REPORT THAT!)`, mensaje declarado no fatal. Según Makefile.webui exacto en upstream 8837853a6, línea ~251 `all` ejecuta reglas std/debug ExtJS; scripts PYTHON (`support/css.py`, rjsmin, etc.) dependen de `.config.mk`. `configure` de ensayo anterior advirtió `WARN: no python binary found`, posible origen pero no confirmado. Próximo paso: inspección read-only `/tmp/g3an-build.log` buscando `make[2]: ***`, `Error N`, `not found`, `Traceback`; inspeccionar `PYTHON` en `.config.mk` y disponibilidad `python`/`python3`. **No ejecutar npm audit fix ni tocar fuentes CUID por este fallo.** `G3AN_CONFIGURE=PASS`, `G3AN_MAKE_WEBUI=FAIL_UNDIAGNOSED`, `G3AN_CUID_COMPILE=NOT_VERIFIED`.

## G3-AN webui build blocker — causa confirmada (22/11/2026)

Diagnóstico operador: `G3AN_CONFIGURE_EXIT=0`, `G3AN_MAKE_EXIT=2`. La primera excepción fatal está en Makefile.webui:278, generación `src/webui/static/tvh.js.gz`: `/bin/sh: 1: python: not found`, Error 127. En `.config.mk`: `PYTHON ?= python`; el ejecutable disponible es `/usr/bin/python3`, pero no existe comando `python` en PATH. Por tanto se trata de dependencia de build, no de error C/CUID. El mensaje `Folder name "Ubuntu 26.04" not found` y aviso de npm no constan como causa fatal identificada. Reanudar sin clean/reconfigure con `make -j2 PYTHON=python3` dentro exclusivamente del checkout aislado `/home/ubuntu/tvheadend-g3an-upstream`, redirigir registro `/tmp/g3an-build-python3.log`. La variable Make de línea de comandos se propaga a submakes. No hacer symlink de python en sistema ni alterar contenedor G3-AM. `G3AN_WEBUI_PYTHON_MISSING=ROOT_CAUSE_CONFIRMED`, `G3AN_MAKE_PYTHON3_RETRY=PENDING`, `G3AN_BUILD=PENDING`.

## G3-AN binario Ubuntu compilado — gate real PASS (22/11/2026)

Operador reanudó build en worktree aislado G3-AN con `make -j2 PYTHON=python3` (sin reinstalar ni alterar G3-AM) y reportó:

    Python 3.14.4
    G3AN_MAKE_EXIT=0
    G3AN_BUILD=PASS
    ./build.linux/tvheadend: version 0.0.0~unknown
    CC timestamp.o
    CC src/docs.o
    CC tvheadend

El compilador y enlazador terminaron con exit 0; queda binario `build.linux/tvheadend`. El version string `0.0.0~unknown` no acredita upstream SHA por sí mismo: mantener trazabilidad por checkout HEAD 8837853a6 + diff aplicado G3-AL/G3-AN. No afirmar que el CUID funciona todavía en runtime, ni que sea seguro en producción. G3-AM mantiene el estado forense de cambio URL con Alpha sustituito y Kodi conectado; G3-AB original no debe tocarse.

Siguiente gate REQUERIDO: desplegar binario G3-AN en **otro** contenedor aislado con volumen nuevo para TVH y playlist sintética exclusiva, puertos HTTP/HTSP distintos de G3-AM 29991/29992 y de G3-AB 19991/19992. No reutilizar config TVH/Kodi ni probar cambios en lista G3-AM. Verificar versión real del binario, copiar plantilla sintética identificada, baseline de canal por CUID y refetch; probar URL query/host/path tras CUID persistido, TVH UUID mux/servicio/canal y Kodi iUniqueId antes/después, cold restart, duplicados y ausencia CUID, reproducción activa. Si UUID cambia, gate FAIL. Mantener el binario en aislamiento hasta gates positivos. Inspeccionar el diff de 229 inserciones y posibles rutas de estado antes de usar siquiera lab de larga duración.

    G3AN_SOURCE_APPLY=PASS
    G3AN_CONFIGURE=PASS
    G3AN_BUILD_UBUNTU=PASS
    G3AN_CUID_RUNTIME=NOT_TESTED
    G3AN_CORELEC_BUILD=NOT_AUTHORIZED

## Runtime separado G3-AN preparado tras compatibilidad Docker PASS

Usuario comprobó mediante `docker run --rm --entrypoint /usr/bin/ldd ... masqelec/tvh-g3am-runtime:noble` que el binario G3-AN enlaza `libssl.so.3`, `libcrypto.so.3`, `libz.so.1`, `libm.so.6`, `libc.so.6`, todas resueltas; `G3AN_DOCKER_LDD_EXIT=0`. GLIBC máxima requerida 2.38 y Ubuntu 24.04 aporta 2.39. El contenedor G3-AM existente seguía `Up 11 hours`. `ldd` PASS comprueba enlace dinámico, NO startup funcional ni compatibilidad de toda la aplicación.

Archivos añadidos en el repo: `lab/pvr_g3ab/g3an/compose.yaml` (proyecto Docker `masqelec-pvr-g3an`, imagen runtime noble ya disponible con **entrypoint G3-AN explícito**, bind mount read-only binario de `/home/ubuntu/tvheadend-g3an-upstream/build.linux/tvheadend`, docs/config assets sólo lectura, config exclusiva `runtime/g3an/tvh_config`, playlist exclusiva `runtime/g3an/playlist`, host HTTP `127.0.0.1:39991`, HTSP `127.0.0.1:39992`, red externa lab existente con alias `g3an-playlist`). `g3an/prepare.py` prepara M3U sintética con `CUID=g3an-001/g3an-002`, etapas `init`, `baseline`, `url`; exige marcador sintético, rechaza symlinks y propietario ajeno, publica atómicamente. La opción `init` NO pisa una playlist ya existente. G3-AB/G3-AM originales no se alteran. No se copian configuraciones o identidades del lab anterior; la configuración TVH arranca vacía y tendrá que crearse su propia red IPTV automática con URL `http://g3an-playlist/playlist.m3u` desde interfaz de laboratorio (sin ACL solo lab). No ejecutar cambio de URL hasta obtener `G3AN_BASELINE_CUID_PERSISTED=PASS` y registro de UUID de mux/servicio/canal; no confiar solo en nombre visible.

Comandos próximos de arranque, con usuario Ubuntu propietario de directorios y Docker funcionando, sin `set -e` en shell interactiva: `git pull --ff-only origin develop`, `python3 service.cloud.masqelec/lab/pvr_g3ab/g3an/prepare.py init`, `docker compose -f service.cloud.masqelec/lab/pvr_g3ab/g3an/compose.yaml config -q`, `docker compose -f ... up -d`, `docker compose -f ... ps`; inspeccionar logs del contenedor específico G3-AN. No ejecutar Docker volume prune/down -v, no tocar puertos G3-AM. Tras boot configurar propia red con URL e inventario, al haber conectado IPTV streams `http://streams/ch*.ts` usando red sintética externa.

GATES: `G3AN_BINARY_LDD_DOCKER=PASS`, `G3AN_COMPOSE_VERSIONED=YES`, `G3AN_RUNTIME_STARTED=NOT_TESTED`, `G3AN_CUID_PERSISTENCE=NOT_TESTED`, `G3AN_KODI_IDENTITY=NOT_TESTED`. El binario G3-AN es experimental y no autorizado para producción.

## G3-AN: arranque runtime Docker comprobado en Ubuntu (22/11/2026)

El operador ejecutó preparación sintética `g3an/prepare.py init`: `G3AN_PLAYLIST_STAGE=BASELINE`, `G3AN_PREPARE_EXIT=0`. `docker compose -f .../g3an/compose.yaml config -q` pasó, y `up -d` arrancó `masqelec-pvr-g3an-playlist-1` y `masqelec-pvr-g3an-tvh-1` con `G3AN_START_EXIT=0`. Mapeo de puertos de contenedor TVH: HTTP `127.0.0.1:39991->9981/tcp`, HTSP `127.0.0.1:39992->9982/tcp`. `curl http://127.0.0.1:39991/` respondió `G3AN_HTTP_CODE=302`. Paralelamente `masqelec-pvr-g3am-tvh-1 Up 11 hours`. Esto acredita **arranque inicial y disponibilidad HTTP**, pero no prueba que HTSP contenga canales ni estabilidad de servicio a largo plazo, ni importación IPTV.

**Siguiente procedimiento:** abrir UI local `http://127.0.0.1:39991/`, crear red de tipo IPTV Automatic Network *solo G3-AN*, URL `http://g3an-playlist/playlist.m3u`, refetch 1 minuto y opciones de scan/mapping según configuración sintética previa; confirmar 2 muxes y sus CUID `g3an-001/g3an-002` en campos de grid o configuración propia. Mapear servicios a canales G3-AN con id autogenerados y capturar UUID pre-URL. Evitar tocar G3-AM/G3-AB, hacer reset de configuración o jugar con Kodi todavía. No ejecutar `g3an/prepare.py url` antes de la captura base y persistencia comprobada.

    G3AN_DOCKER_LDD=PASS
    G3AN_RUNTIME_START=PASS
    G3AN_HTTP_RESPONDS=YES_302
    G3AN_NETWORK_CREATED=PENDING
    G3AN_CUID_BASELINE_PERSISTENCE=PENDING
    G3AN_URL_CHANGE=PENDING

## HTTP 500 diagnosticado — Vue dist no montado (22/11/2026)

Runtime G3-AN `tvh` y `playlist` Up 2min, API `/api/serverinfo` 200, `/gui/` 500. Logs G3-AN: `[ERROR] webui: failed to open src/webui/static-vue/dist/index.html`. Sólo se había montado el directorio ExtJS `src/webui/static` y recursos `data/conf`; no la salida Vue. Se corrigió `g3an/compose.yaml` añadiendo bind mount de `/home/ubuntu/tvheadend-g3an-upstream/src/webui/static-vue/dist` a `/opt/src/webui/static-vue/dist` `:ro`. Antes de recrear exclusivamente servicio TVH G3-AN, exigir `test -f /home/ubuntu/tvheadend-g3an-upstream/src/webui/static-vue/dist/index.html`; si no existe, bloquear y diagnosticar Vue build, NO permitir creación implícita de directorio vacío por Compose. `docker compose -f ... up -d --no-deps tvh` recreará sólo G3-AN TVH, conservando volumen bind `runtime/g3an/tvh_config`, sin tocar G3-AM o G3-AB. Verificar `/gui/` y API tras arranque. Este HTTP 500 no apunta al código CUID, pero el runtime funcional CUID permanece pendiente.

    G3AN_RUNTIME_PROCESS=PASS
    G3AN_API_SERVERINFO=200
    G3AN_WEBUI_GUI=500_MISSING_VUE_DIST
    G3AN_VUE_MOUNT_CODE=COMMITTED
    G3AN_VUE_DIST_EXISTS_ON_HOST=UNVERIFIED
    G3AN_WEBUI_RETEST=PENDING

## Vue GUI corregida y verificada (22/11/2026)

Salida real del operador tras `g3an/compose.yaml` actualizado: `G3AN_VUE_DIST=PASS`; `docker compose up -d --no-deps tvh` recreó exclusivamente `masqelec-pvr-g3an-tvh-1`; `G3AN_GUI_HTTP=200`, `G3AN_API_HTTP=200`; G3-AM original permanecía `Up 11 hours`. Se cierra el bloqueo HTTP 500 por falta de montaje `/opt/src/webui/static-vue/dist`. La UI Vue está disponible. En un HTML SingleFile suministrado por operador se observa vista `Channels: 2`, pero no sustituye inventario de UUID/CUID persistente por API o en la configuración. No ejecutar mutación URL hasta captura basal de muxes, servicios y canales y comprobación `iptv_cuid` de los dos muxes.

    G3AN_VUE_DIST=PASS
    G3AN_GUI_HTTP=200
    G3AN_API_HTTP=200
    G3AN_G3AM_UNTOUCHED=YES
    G3AN_CUID_BASELINE_PERSISTENCE=PENDING

## G3-AN baseline de identidades reales por API (22/11/2026)

Operador proporcionó API G3-AN con 2 muxes, ambos con campo modificado `iptv_cuid` visible: Alpha `g3an-001` UUID mux `afa32f8f8223bdff59057f7790448c92`, URL `http://streams/ch1.ts`; Beta `g3an-002` UUID mux `c96721109b182b2d53fbba80bdc5820c`, URL `http://streams/ch2.ts`. Dos canales: Alpha UUID `e4852534cdb2fd64f54fd861d4d00767`, número 1; Beta UUID `0d3bd243f67184e9adb9ceadf4a51c50`, número 2. Servicios vinculados: Alpha `4bfccf27c63505a1b6b81aec861174ed` (svcname `G3AB Signal 1` sid 1), Beta `0588b5c02d512b7045c254cf95ed46ab` (svcname `G3AB Signal 2` sid 2). **Tercer servicio** no vinculado `923fc082cf4b92edf42d4b5a87da125e`, svcname `G3AN Beta`, sid 1; posible provisional, no borrar ni ignorar en invariantes. `G3AN_BASELINE_INVENTORY=COMPLETED`, `G3AN_CUID_API_PRESENT=PASS`. Persistencia CUID tras reinicio, total de servicios después de refetch, preservación de UUID de mux/service/channel y Kodi HTSP iUniqueId siguen PENDIENTES.

**Próximo gate:** comprobación directa read-only de ficheros `/config/input/iptv/muxes` o equivalente y snapshot API en fichero fuera de G3-AM, sin cambiar URL. Si el CUID persistió, probar reload/restart limitado a G3-AN y comparar UUID/cuid. Después ejecutar `prepare.py url`, forzar refresco o esperar periodicidad y comparar identidades/total de servicios. En las primeras pruebas observar la condición de seguridad `mm_active` e interrumpir ante cualquier cambio de UUID. No declarar plenamente funcional hasta medir todos los gates, especialmente Kodi.
