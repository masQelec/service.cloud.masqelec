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
