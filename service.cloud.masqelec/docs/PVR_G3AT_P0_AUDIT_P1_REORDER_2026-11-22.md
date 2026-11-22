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
