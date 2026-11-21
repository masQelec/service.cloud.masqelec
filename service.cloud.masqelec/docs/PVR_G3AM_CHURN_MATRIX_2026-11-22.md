# G3-AM — matriz controlada de cambios M3U (22/11/2026)

## Estado de partida
G3-AM Tvheadend parcheado y Kodi 21.3 + pvr.hts 21.2.6. Renombrado reversible de Alpha: PASS extremo a extremo. Base de Kodi TV46.db: Beta idChannel 1 / iUniqueId 1473024293, Alpha idChannel 2 / iUniqueId 1699146942. UUID TVH Alpha beec46e5ab595d2474289e74c9ab9849, Beta 2591ccd729867bffc24e8f4bd8b765af. Dos canales, sin duplicados.

## Alcance
Herramienta tools/pvr_g3am_matrix.py: guarda marcador sintético, rutas privadas G3-AM, estado inicial de los dos canales TVH y Kodi. Sólo sustituye atómicamente la M3U sintética de G3-AM; lee API TVH y SQLite Kodi en mode=ro. No modifica G3-AB, bases Kodi, mapeos TVH, ni CoreELEC.

## Ejecutar en Ubuntu, con Kodi G3-AM abierto conectado a 29992

    cd /home/ubuntu/GitHub/service.cloud.masqelec
    git pull --ff-only origin develop
    python3 -m py_compile service.cloud.masqelec/tools/pvr_g3am_matrix.py
    python3 service.cloud.masqelec/tools/pvr_g3am_matrix.py --preflight
    set -o pipefail
    python3 -u service.cloud.masqelec/tools/pvr_g3am_matrix.py --run safe | tee /tmp/g3am-matrix-safe.log

Fase safe: invertir filas M3U, cambiar group-title Alpha y restaurar la playlist original, manteniendo nombres, números y CUID. Cada fase deja 75s de margen para el refetch periódico. Evalúa que Tvheadend y Kodi conservan UUID, ID interno, iUniqueId, nombres y exactamente dos canales. Si G3AM_SAFE_IDENTITY=PASS, únicamente está validada conservación de identidad; **no equivale a verificar propagación real de grupos o orden a Kodi**, pendiente de instrumentación.

## Exploración URL — no lanzar sin revisar resultado safe
La opción --run url-probe repite fases safe y luego cambia la URL de Alpha a ch1.ts?g3am_url_test=1, conservando CUID. Observa TVH/Kodi y se detiene obligatoriamente con G3AM_MATRIX=STOP_FOR_OPERATOR_REVIEW (exit 3). No calificar esto como PASS. Puede aparecer un mux nuevo, servicio distinto o perderse la asociación; no proceder automáticamente con altas/bajas o limpieza. Para restaurar sólo la playlist nominal (NO estado TVH) usar g3am/prepare.py rename tras inspección.

    set -o pipefail
    python3 -u service.cloud.masqelec/tools/pvr_g3am_matrix.py --run url-probe | tee /tmp/g3am-matrix-url.log

La herramienta todavía no se ha probado en el Ubuntu del operador. No subir datos runtime, DB, ni PCAP.

Gates: G3AM_RENAME_E2E=PASS; G3AM_MATRIX_SAFE_UBUNTU=PENDING; G3AM_ORDER_GROUP_PROPAGATION=PENDING; G3AM_URL_IDENTITY=PENDING; G3AM_ADD_REMOVE=PENDING; G3AM_CORELEC_BUILD=PENDING.

## Resultado real de fase safe (22/11/2026)

El operador ejecutó dos preflight PASS y los tres escenarios con resultados:

    G3AM_MATRIX_PREFLIGHT=PASS
    MATRIX_STAGE=reorder PLAYLIST_ONLY=YES
    OBSERVE stage=reorder t=0s tvh=2 services=3 kodi=[(1,1473024293,'G3AM Beta'),(2,1699146942,'G3AM Alpha Renamed')] reason=STABLE
    STAGE=reorder RESULT=IDENTITY_ONLY
    MATRIX_STAGE=group PLAYLIST_ONLY=YES
    OBSERVE stage=group t=0s tvh=2 services=3 kodi=[(1,1473024293,'G3AM Beta'),(2,1699146942,'G3AM Alpha Renamed')] reason=STABLE
    STAGE=group RESULT=IDENTITY_ONLY
    MATRIX_STAGE=restore PLAYLIST_ONLY=YES
    OBSERVE stage=restore t=0s tvh=2 services=3 kodi=[(1,1473024293,'G3AM Beta'),(2,1699146942,'G3AM Alpha Renamed')] reason=STABLE
    STAGE=restore RESULT=IDENTITY_ONLY
    G3AM_SAFE_IDENTITY=PASS
    G3AM_GROUP_AND_ORDER_PROPAGATION=UNVERIFIED

Por diseño los 75 segundos de cada etapa cubren nominalmente el refetch de 60 segundos, pero los reportes solo presentan identidad al t=0 de la *ventana de observación posterior*, no demuestran cuándo/si se procesó cada refetch; no afirmar actualización real de agrupación o posición. Canal y servicios siguen cardinalidad TVH 2/3, Kodi 2. UUID/idChannel/iUniqueId conservados.

La siguiente operación de mayor riesgo es cambiar URL de Alpha manteniendo CUID. Se añadió opción `--run url-only` al ejecutor para no repetir las tres fases safe: requerirá `--preflight` tras actualizar develop, publicará solo la URL variante en la playlist sintética y observará hasta 150 segundos. La herramienta termina intencionalmente con retorno 3 `G3AM_MATRIX=STOP_FOR_OPERATOR_REVIEW` sin modificar DB ni mapeos, independientemente de que el resultado sea revisión o timeout. Es imprescindible registrar `OBSERVE`, servicio/mux y canales posteriores antes de decidir restauración y alta/baja; el estado nominal restored es el prerequisito. No ejecutar `url-probe` redundante si ya se superó safe.

GATES: G3AM_SAFE_IDENTITY=PASS; G3AM_GROUP_PROPAGATION=UNVERIFIED; G3AM_ORDER_PROPAGATION=UNVERIFIED; G3AM_URL_CHANGE=NOT_TESTED.

## Hallazgo CRÍTICO: cambio de URL rompe identidad (22/11/2026)

El operador ejecutó `--run url-only` desde estado nominal. PRECHECK PASS; a los 55 segundos del refetch, `G3AM_MATRIX=STOP_FOR_OPERATOR_REVIEW` (exit 3 previsto) y se observó `reason=TVH_UUID_SET`. Evidencias:

    PRE-TVH Alpha channel UUID=beec46e5ab595d2474289e74c9ab9849
    PRE-TVH Alpha service UUID=66f63f4e1a9d19a643a806990433bb8c
    PRE-Kodi Alpha iUniqueId=1699146942 idChannel=2
    POST-TVH Alpha channel UUID=7b9c2895a5ecc78d3289b36f02e4d4a9
    POST-TVH Alpha service UUID=80bb0e985faf016596abd82310e2d8b8
    POST-Kodi Alpha iUniqueId=354983035
    POST-TVH muxes COUNT=2; services COUNT=3; channels COUNT=2
    POST-TVH Beta UUID=2591ccd729867bffc24e8f4bd8b765af; service=68a79db48e632d6a766b7eee25d97458

**G3AM_URL_IDENTITY=FAIL**, pese a mismo CUID `g3am-001`, nombre/número y cardinalidad dos. Hubo reemplazo efectivo de servicio y canal, aunque no duplicado visible. `idChannel` de Alpha posterior no se incluyó en salida del operador: no afirmar si ese ID se conserva o cambió.

### Causa de fuente verificada contra upstream exacto tvheadend@8837853a6

En `src/input/mpegts/iptv/iptv_auto.c`, función `iptv_auto_network_process_m3u_item`: línea ~223-225 recorre muxes existentes y decide coincidencia exclusivamente comparando `mm_iptv_url_cmpid` (fallback URL) contra `url2`; línea ~288-325 crea un mux nuevo cuando no encuentra coincidencia. El procesador del playlist en ~412-435 marca todos los muxes para borrar antes del parseo y borra aquellos que nunca fueron matcheados. La función lee `m3u-url`, nombre, tvg/tvh-number, tvg-id, tvh-tags/group-title, logo, etc. pero **no lee el atributo CUID para la clave de identidad del mux**. Nuestro parche G3-AL solo añade `channelUpdate` en la rama de URL ya coincidente; no aborda cambios de URL. Por ello la recreación al cambiar `?g3am_url_test=1` es coherente con la lógica fuente. Es hipótesis de causalidad completa muy sólida, y el efecto está observado en laboratorio. No concluir que todos los IPTV o todas las configuraciones sufren esto: opciones `ignore_args`/ignore_path pueden modificar la clave de comparación, pero no son solución general si cambia host, path u otras partes.

### Decisión de seguridad

**No restaurar todavía playlist, reiniciar Kodi/TVH, borrar canal/servicios, ni ejecutar altas/bajas**, para conservar estado de fallo. Primero capturar inventario read-only de post-cambio incluyendo `idChannel,iUniqueId,name`, estado URL/clave mux mediante API y documentación fuente. Proponer ID estable basado en CUID solo después de diseñar semántica de duplicados, atributo ausente, convivencia con instalaciones existentes, garantía de unicidad por red y migración segura de muxes; no es válido simplemente reutilizar nombre/posición de lista. No pasar parche nuevo a CoreELEC sin gate por URL y restauración.

    G3AM_URL_CHANGE=FAIL
    G3AM_URL_POST_TVH_CHANNEL_REPLACED=YES
    G3AM_URL_POST_SERVICE_REPLACED=YES
    G3AM_URL_POST_KODI_IUNIQUEID_REPLACED=YES
    G3AM_URL_POST_KODI_IDCHANNEL=UNKNOWN
    G3AM_PATCH_G3AL_RENAME=PASS
    G3AM_URL_IDENTITY_FIX=NOT_IMPLEMENTED

## Confirmación forense final de URL (22/11/2026)

Captura operador:

    KODI idChannel=1 iUniqueId=1473024293 iClientId=1 sChannelName='G3AM Beta'
    KODI idChannel=2 iUniqueId=354983035 iClientId=1 sChannelName='G3AM Alpha Renamed'
    KODI CHANNEL_COUNT=2
    MUX Alpha uuid=ec0791b576f077922360e490e2abc68b name='playlist.m3u - G3AM Alpha Renamed' iptv_url='http://streams/ch1.ts?g3am%5Furl%5Ftest=1' iptv_url_cmpid=same
    MUX Beta uuid=4dc2e4d79e413d1df42cef0239e4e5ab iptv_url='http://streams/ch2.ts' cmpid=same
    G3AM_POST_URL_FORENSICS=COMPLETED

La API confirmó cambio de mux UUID (anterior de Alpha no consta en inventario previo de este documento) y ya se había comprobado cambio de servicio y canal UUID. En Kodi **idChannel=2 siguió estable**, pero **iUniqueId cambió 1699146942→354983035**. La ausencia de duplicados no compensa pérdida de identidad PVR. El guion bajo escapado como `%5F` es parte de la normalización del parser, no evidencia de identidad por sí sola.

### Nueva inspección upstream exacta 8837853a6

`src/misc/m3u.c:142-169` conserva atributos arbitrarios de `#EXTINF` en el `htsmsg` bajo su nombre literal. **CUID sí llega al mapa de entrada**, pero `src/input/mpegts/iptv/iptv_auto.c:93-143,223-325` nunca lo lee: localiza mux por URL de comparación, crea uno cuando cambia y borra el antiguo en `iptv_auto_network_process` (~412-435). `src/input/mpegts/iptv/iptv_mux.c:39-82` tiene setter `iptv_url_set(&im->mm_iptv_url,&im->mm_iptv_url_sane,...)` que normaliza/actualiza ambos campos; `iptv_url_cmpid` es propiedad string oculta independiente (`iptv_mux.c:154-159`). **No basta con asignar directamente `mm_iptv_url`**: actualizar coherentemente ambos valores y persistencia del mux, respetar posibles entradas activas y todo el ciclo de streaming.

Diseño de cambio todavía NO implementado: identificador IPTV explícito del mux, persistente y único por red; búsqueda prioritariamente por CUID válido y no duplicado, fallback URL sin CUID; adopción/migración de mux existente sin CUID solo con mapeo inequívoco; en coincidencia CUID actualizar URL vía setter nativo y comparación, conservando mux/servicio/canal UUID; no borrar/recrear canales. Rechazar CUID duplicados/ambiguos y no alterar estado ante listas inválidas. Considerar que `CUID` es una convención de esta lista, no identificador universal o estándar de todos los proveedores. Test con URL que cambia de host, path y query; etapas de rollback, posible streaming activo y persistencia tras reinicio. Lo anterior es **diseño hipotético pendiente de revisión de ciclo de vida**; no atribuir PASS ni implementarlo precipitadamente.

**Estado conservado:** playlist Alpha apunta a URL con query `g3am_url_test`, Kodi y TVH tienen nuevas identidades; no restaurar ni limpiar TVH por ahora. No comenzar altas/bajas hasta definir tratamiento de identidad estable.

    G3AM_URL_CHANGE_IDENTITY=FAIL_CONFIRMED
    G3AM_KODI_IDCHANNEL_STABLE=YES_2
    G3AM_KODI_IUNIQUEID_CHANGED=YES
    G3AM_URL_ROOT_CAUSE=URL_BASED_MUX_MATCH_SOURCE_VERIFIED
    G3AM_CUID_PARSER_PROPAGATES_ATTRIBUTE=YES
    G3AM_CUID_USED_AS_MUX_ID=NO
    G3AM_CUID_PATCH_DESIGN=OPEN
