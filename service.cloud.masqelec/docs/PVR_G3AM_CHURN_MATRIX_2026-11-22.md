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
