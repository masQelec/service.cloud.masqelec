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
