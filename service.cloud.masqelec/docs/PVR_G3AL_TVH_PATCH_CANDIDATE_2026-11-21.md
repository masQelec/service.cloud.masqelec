# G3-AL — Candidato de parche Tvheadend: notificación HTSP selectiva tras rename IPTV

**Fecha:** 2026-11-21. **Objetivo:** demostrar que la modificación de un nombre efectivo recibida de M3U produce `channelUpdate` en el **mismo socket HTSP** y que Kodi mantiene sus IDs, sin reiniciar PVR, hacer rescan del bouquet ni escribir en SQLite.

## Estado real

```text
G3AL_CANDIDATE_PATCH_COMMITTED=YES
G3AL_PATCH_EXACT_SOURCE_HUNKS_VERIFIED=5
G3AL_GIT_APPLY_CHECK_ON_UBUNTU=PENDING
G3AL_COMPILATION=PENDING
G3AL_RUNTIME_TEST=PENDING
G3AL_PRODUCTION_AUTHORIZED=NO
G3AL_PRODUCTION_DEPLOYED=NO
```

Archivo: `lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch`. **NO está aplicado al contenedor Tvheadend** ni se ha construido nueva imagen. Los cinco hunks se han contrastado uno a uno contra `tvheadend/tvheadend@8837853a6`; falta el `git apply --check` de una copia real en Ubuntu y la compilación.

## Fundamento de revisión fuente exacta

- `src/input/mpegts/iptv/iptv_auto.c`: en un multiplexor existente con URL coincidente, cambia `im->mm_iptv_svcname`, pero solo notifica al idnode del mux, no a canales HTSP.
- `src/input/mpegts/iptv/iptv_service.c`: `iptv_service_channel_name()` devuelve `im->mm_iptv_svcname` dinámicamente si no vacío; la consulta de nombre efectivo del canal puede cambiar sin tocar nombre persistente.
- `src/channels.c`: `channel_get_name()` prefiere nombre fijo `ch_name`, o nombre de servicio enlazado; `autoname=True` para los dos canales de G3-AB.
- `src/input/mpegts/mpegts_mux.c`: `mm_services` / `s_channels` permiten encontrar **solo canales enlazados**.
- `src/htsp_server.c`: `htsp_channel_update(ch)` envía `channelUpdate` a clientes HTSP asíncronos autorizados; no modifica mapping.
- `src/download.c`: descarga HTTP ejecuta callback M3U bajo `global_lock`. **Candidato restringe notificación a `http://` y `https://`**, no a rutas file/pipe todavía no auditadas.

## Comportamiento candidato

Cuando cambie `mm_iptv_svcname` en multiplexor existente:

1. Antes de cambiarlo, tomar snapshot solo de los canales asociados a sus servicios que tengan `ch_autoname` activado y sin `ch_name` fijo. Deduplicar por puntero `channel_t*`.
2. Guardar nombre efectivo previo usando `channel_get_name()`. Si falla reserva de memoria, continuar recarga normal **pero no enviar notificaciones parciales**.
3. Cambiar valor de `mm_iptv_svcname` usando lógica existente, sin tocar `ch_name`, enlaces, bouquets, base de datos ni ID.
4. Para cada canal en snapshot, comparar nombre efectivo actual contra nombre previo y llamar a `htsp_channel_update(ch)` **solo si cambió**.
5. Liberar siempre el snapshot. Repetir M3U idéntica no debe producir notificaciones; cambios ajenos al nombre conservan comportamiento previo.

**No es seguro generalizar este candidato a todos los sistemas sin laboratorio**: no se ha demostrado compilación, comportamiento cuando varios servicios comparten canal, que los tags/LCN/hot order tengan el mismo defecto, ni compatibilidad de CoreELEC. La notificación del nombre no resuelve por sí sola eliminación/orden de canales en Kodi.

## Preflight EXCLUSIVAMENTE offline en Ubuntu

Desde `/home/ubuntu/GitHub/service.cloud.masqelec`:

```bash
git pull --ff-only origin develop

# No utilizar el árbol del addon para el checkout upstream.
cd /home/ubuntu

if [ ! -d tvheadend-g3al-upstream/.git ]; then
  git clone --filter=blob:none https://github.com/tvheadend/tvheadend.git tvheadend-g3al-upstream
fi
cd tvheadend-g3al-upstream
git fetch --filter=blob:none origin
git checkout --detach 8837853a6

git status --short
git rev-parse --short=9 HEAD

git apply --check \
  /home/ubuntu/GitHub/service.cloud.masqelec/service.cloud.masqelec/lab/pvr_g3ab/patches/tvheadend-8837853a6-g3al-channel-notify.patch

echo "G3AL_PATCH_APPLY_CHECK=PASS"
```

**Precaución:** `git clone` y `git fetch` requieren Internet; si falla acceso o la revisión no coincide, `G3AL_BLOCKED`. `git apply --check` **no modifica archivos**. No ejecutar todavía `git apply` sobre el checkout, ni desplegar imagen. El subdirectorio `_lab_upstream` es un árbol separado, no debe añadirse al repositorio; al estar dentro del repo del addon puede aparecer como carpeta sin seguimiento: mantener fuera de commits.

**Límites del gate**: el preflight es solo comprobación estructural; la compilación y validación HTSP requieren otro gate y decisión explícita de sustituir el **contenedor de laboratorio** con rollback, nunca `latest` en producción.

## Plan del gate runtime posterior (no ejecutado)

- Preparar copia de configuración/estado G3-AB + imagen derivada `tvheadend:g3al-lab`, no reusar `latest`; conservar Docker config persistente y poder revertir.
- Mantener sesión HTSP abierta y capturar `channelUpdate` mediante G3-AH, con SYN/puertos del cliente invariantes durante `prepare.py rename` → importación M3U.
- Comprobar nombre Kodi renombrado sin reproducción ni reconexión y `channelid=3`/Beta=2; conservar UUID, servicios, autoname, protección de grupos, sin pérdidas.
- Probar rename inverso, M3U sin cambio, múltiple servicio, iconos/tags separados y replay de corte sin propagación de IDs.
- Abortar ante falla de invariantes y conservar PCAP privado.

## Riesgos a evaluar

- Es una modificación de Tvheadend, no del addon. Necesitaría distribución, mantenimiento y actualización de un binario diferente para usuarios de masQelec.
- No inferir que CUID M3U equivale a identificador Tvheadend/Kodi.
- La actualización de nombre no valida aún la gestión integral del mantenimiento PVR (eliminación, cambio de URL, orden y grupos). La transición completa no está autorizada.
