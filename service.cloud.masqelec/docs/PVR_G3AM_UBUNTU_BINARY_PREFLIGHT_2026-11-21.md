# G3-AM — Preflight de binario Ubuntu y laboratorio paralelo (21/11/2026)

## Alcance
Continuación de G3-AL. Evidencia aportada por el operador desde Ubuntu, comandos de solo lectura. No se ha lanzado el binario parcheado, ni creado una segunda instancia, ni modificado Tvheadend/Kodi/playlist originales.

## Evidencia observada
- Laboratorio: `/home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab`.
- `docker compose ps`: `masqelec-pvr-g3ab-tvh-1` y `masqelec-pvr-g3ab-streams-1` activos (Up 10 hours), ambos con cero acciones de reinicio reportadas en este gate.
- TVH original: `lscr.io/linuxserver/tvheadend:latest`, `linux/amd64`, ID visible `7f5d04ed7ea7`, puertos loopback `19991:9981`, `19992:9982`.
- Streams: `nginx:alpine`, `linux/amd64` sin puerto publicado.
- Existen marcador sintético, playlist, configuración TVH, perfil Kodi y las dos capturas HTSP previas. Existencia no equivale a validar contenidos.
- Checkout: `/home/ubuntu/tvheadend-g3al-upstream`, HEAD `8837853a6`; git status ` M src/input/mpegts/iptv/iptv_auto.c` (parche aplicado).
- Ejecutable: `build.linux/tvheadend`; `file` ELF 64-bit PIE x86-64, GNU/Linux glibc dinámico (`/lib64/ld-linux-x86-64.so.2`), no stripped.
- `ldd` resuelve `libssl.so.3`, `libcrypto.so.3`, `libz.so.1`, `libm.so.6`, `libc.so.6`, `libzstd.so.1`. No reportó ninguna biblioteca `not found` **en el host**.
- `--version`: `4.3-2897~g8837853a-dirty`; sufijo dirty compatible con el parche local.
- SHA-256 del binario: `b94c205632ab1dc8ad8e4d71d9c127ddae518fd28c3381919b5974de65aa753a`.
- El comando de preflight terminó con `G3AM_READ_ONLY_PREFLIGHT=COMPLETED`, que es marcador de recorrido, **no** acreditación automática de todos los invariantes.

## Conclusión limitada
`G3AM_HOST_BINARY_ARCH=PASS_X86_64`; `G3AM_HOST_LDD_RESOLUTION=PASS`; `G3AM_VERSION=PASS_VERIFIED`.
**No** está demostrada compatibilidad de ABI/runtime con contenedor LinuxServer, capacidad de aceptar HTSP, envío de `channelUpdate`, actualización de Kodi o preservación de IDs. Configuración host compilada con funciones reducidas respecto a distribución final.

## Siguiente gate: aislamiento — primero inventario read-only
1. Confirmar puertos candidatos `127.0.0.1:29991/29992` libres y la topología de red y modo de acceso a `http://streams/ch1.ts` sin publicar credenciales.
2. Evaluar host glibc + configuración aislada frente a nuevo contenedor builder/runtime compatible. No copiar binario Ubuntu directamente a LinuxServer.
3. Planificar snapshot/copia privada de configuración, referencias de playlist y cliente Kodi separado; mantener intactos `runtime/tvh_config`, `runtime/kodi_home/.kodi` y los puertos originales.
4. No ejecutar `prepare.py` en el laboratorio original ni iniciar servidores paralelos hasta establecer aislamiento y rollback.
5. Posteriormente demostrar `channelUpdate` en **misma sesión HTSP** sin SYN/reconexión, respuesta Kodi sin playback, y preservación de UUID, servicios, identificadores Kodi, autoname, grupos/favoritos. Comparar antes/después en instancia aislada; no tratar UUID anteriores como obligatorios si la instancia se ha inicializado con otros.
6. Sin modificar production/CoreELEC. EPG-01 queda para fase posterior.

## Estados
```
G3AM_LAB_COMPOSE_RUNNING=PASS_OBSERVED
G3AM_LAB_STATE_FILES=PRESENT
G3AM_HOST_BINARY_ARCH=PASS_X86_64
G3AM_HOST_DEPENDENCIES=PASS_LDD_NO_MISSING
G3AM_BINARY_VERSION=4.3-2897~g8837853a-dirty
G3AM_BINARY_SHA256=b94c205632ab1dc8ad8e4d71d9c127ddae518fd28c3381919b5974de65aa753a
G3AM_BINARY_RUNTIME=NOT_TESTED
G3AM_PARALLEL_TVH=NOT_STARTED
G3AM_HTSP_HOT_RENAME=NOT_TESTED
G3AM_KODI_UPDATE=NOT_TESTED
G3AM_CORELEC_BUILD=NOT_STARTED
G3AM_PRODUCTION_DEPLOY=NO
```

Documentos: `HANDOFF_TVH_CUSTOM_CORELEC_EPG_2026-11-21.md`, `RUNBOOK_G3AB_UBUNTU_LAB_2026-11-21.md`, `PVR_G3AL_TVH_PATCH_CANDIDATE_2026-11-21.md`.
