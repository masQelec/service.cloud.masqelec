# G3-AK — Revisión de propagación M3U → canal → HTSP (2026-11-21)

## Evidencia consolidada (laboratorio aislado)

En Tvheadend `4.3-2897~g8837853a6`, imagen LinuxServer `8837853a-ls288` sha256:`7f5d04ed7ea7f58cd50c2cf11a79d0823fa0a4aa4f6c64478360b9e3a8027c28`, el operador confirmó:

| Canal | UUID | Servicio | autoname | enabled |
| --- | --- | --- | --- | --- |
| G3AB Alpha Renamed | dba29285ca808eb6486d364f994b05db | e98c6fdf8c5a5e16e3ea122319f9977b | true | true |
| G3AB Beta | 3bf90ae8eb828a6e4961902724a1f380 | afe6f317e9b95eb03f6d91691e80f537 | true | true |

Durante refetch rename Tvheadend mostró Alpha Renamed pero Kodi mantuvo label antiguo y la captura HTSP existente no tuvo payload (32 paquetes, 0 payload según parser, conteo anterior tcpdump 28). En playback hubo **nuevas conexiones TCP** 49262/40098, cada una con **2 mensajes HTSP `channelAdd` estructuralmente válidos + 1 `initialSyncCompleted`**, nombres e IDs HTSP presentes; Kodi finalmente mostró el label nuevo con IDs Kodi estables (Alpha=3/Beta=2). Herramienta G3-AH: 12/12 tests Ubuntu OK, sin frames inválidos ni gaps de reconstrucción en nuevas sesiones. En el PCAP no se validó evento `channelUpdate`.

## Revisión de código EXACTO `tvheadend/tvheadend@8837853a6`

1. `src/input/mpegts/iptv/iptv_auto.c:225-283`: la rama de multiplexor existente (comparación URL `mm_iptv_url_cmpid`) detecta cambio de nombre de la M3U, sustituye `im->mm_iptv_svcname` y llama a `idnode_notify_changed(&im->mm_id)`. **No llama directamente a evento HTSP del canal.**
2. `src/idnode.c:1219-1250`: `idnode_notify_changed` es notificación de idnode y no equivale a `idnode_changedfn`; una escritura sin cambios no garantiza invocar callback `channel_class_changed`.
3. `src/channels.c:78-94`: `channel_class_changed` ejecuta `htsp_channel_update(ch)`; `channel_get_name` toma `ch_name` si no vacío o cae al nombre de servicio; `autoname=True` en ambos canales del lab.
4. `src/htsp_server.c:3783-3835`: `htsp_channel_update` emite `channelUpdate` hacia sesiones HTSP async autorizadas.
5. `src/input/mpegts/mpegts_mux.c:340-360`: multiplexor tiene `mm_services` (`LIST_FOREACH(s, &mm->mm_services, s_dvb_mux_link)`), y cada servicio tiene `s_channels` (`LIST_FOREACH(ilm, &s->s_channels, ilm_in1_link)`). **Existe ruta estructural para localizar los canales afectados sin recorrer todos los canales del sistema ni buscar por nombre**.
6. `src/bouquet.c`: `bouquet_map_channel`, `bouquet_unmap_channel` pueden mapear/desmapear y `channel_delete` en determinadas condiciones. **Descartado bouquet rescan como trigger artificial seguro**. El código de `iptv_auto.c` llama `mpegts_network_bouquet_trigger` cuando cambia LCN, no por simple nombre.
7. `src/channels.c:130-150,271-291`: escribir `name` sobre canal con `autoname=True` puede fijar nombre y romper futuras actualizaciones. **No usar**.

## Hipótesis causal

Durante rename M3U sobre URL estable, el servidor cambia metadatos del mux/servicio y su nombre efectivo, pero no genera `channelUpdate` en sesión HTSP preexistente. En reconexión posterior, `channelAdd` inicial exporta el nombre nuevo. **Muy consistente con evidencia, no completamente cerrado:** falta instrumentar ruta de callbacks indirectos y verificar lock del hilo descarga.

## Propuesta de parche experimental EN FUENTE TVH, NO AUTORIZADO PARA PRODUCCIÓN

En rama de mux existente en `iptv_auto_network_process_m3u_item`, cuando `mm_iptv_svcname` **cambie de verdad**:

- Registrar internamente el cambio de nombre (boolean dedicado, no reutilizar `change` que también incluye iconos, URL, tags, prioridades).
- Tras actualizar metadatos y cuando el nombre efectivo del canal ya refleje el nuevo servicio, localizar los servicios del `mm` y canales enlazados mediante `mm_services` y `s_channels`.
- Emitir únicamente para canales `ch_autoname=True` y cuyo **nombre efectivo cambió**; evitar emitir mensajes duplicados por más de un servicio/canal y evitar canales con nombre fijo o no autorizados.
- Llamar a la ruta nativa `htsp_channel_update(ch)`, **solo con `global_lock` correctamente retenido**, respetando las precondiciones de `_htsp_channel_update`. No llamar fuera de contexto ni desde un hilo arbitrario: confirmar el lock y el ciclo de vida antes de diseñar el diff.
- No modificar `ch_name`, `autoname`, `ch_bouquet`, mappings, servicios, UUID, mux URLs ni la base de datos de Kodi. No cambiar comportamiento de eliminación de canales.
- Por principio solo-notificación: el envío HTSP no debería guardar ni alterar la configuración de canales. Si un servicio se renombra pero el canal tiene un nombre fijo, no notificar por nombre.
- Si no se puede demostrar el callback seguro y la deduplicación, **bloquear el parche**, no forzar API writes ni reinicios PVR.

**La propuesta anterior es un diseño, no un parche probado.** La mera condición `mm_iptv_svcname changed` no garantiza que el nombre efectivo del canal haya cambiado; la comparación previa/posterior y la herencia deben verificarse en compilación/pruebas.

## Gates obligatorios de G3-AL antes de compilar parche

1. Confirmar con fuente exacta el contexto del hilo de `download_init(...).process=iptv_auto_network_process` y si dispone de `global_lock` cuando se recorre `mm_services`/se llama `htsp_channel_update`. Verificar que no hay lock inverso o races con destrucción.
2. Verificar rutas de refresco de nombre del servicio para IPTV, que `channel_get_name` refleja el valor nuevo antes de notificar.
3. Construir patch contra `8837853a6`; `git apply --check`, compilar y ejecutar tests sobre **imagen derivada etiquetada únicamente para laboratorio**, nunca sustituir etiqueta `latest` directamente.
4. Prueba rename aislada con conexión HTSP previa **mantenida**: exige `channelUpdate` válido desde TVH a mismo socket y actualización Kodi sin nuevas conexiones, mismo UUID TVH, mismo services, mismos IDs Kodi, `autoname=True`, Beta intacta. Watcher 40 muestras; no reproducir canal para inducir reconexión.
5. Test volver al nombre original y segundo rename, además de refetch M3U sin cambios (cero falsos eventos), grupos protegidos intactos, URL cambios y orden independientes. No recrear bouquet.
6. Gate negativo: error, caída TVH, pérdida IDs, cambio de `autoname`, reconexión PVR, drop de servicio, o difusión de secretos → `G3AL_BLOCKED`.

## Decisión de arquitectura pendiente

Una imagen Tvheadend personalizada implica mantenimiento de versión en cada actualización LinuxServer y compatibilidad con CoreELEC/masQelec. Antes de producción, comparar coste y fiabilidad con una **API oficial de refresh específica de canal si existe**. No hay una API no-op segura probada; no se debe asumir que `idnode/save` sin cambios desencadena `htsp_channel_update`.

## Estado

```text
G3AK_EXACT_SOURCE_REF=8837853a6
G3AK_AUTONAME_ALPHA_BETA=TRUE
G3AK_MUX_TO_CHANNEL_LINKS_IN_SOURCE=VERIFIED
G3AK_BOUQUET_REFRESH_SAFE=NO
G3AK_NOOP_CHANNEL_NAME_WRITE_SAFE=NO
G3AK_PATCH_COMPILED=NO
G3AK_HTSP_PUSH_PATCH_LAB_VERIFIED=NO
G3AK_PRODUCTION_MODIFIED=NO
G3AK_NEXT=VERIFY_DOWNLOAD_THREAD_LOCK_AND_SERVICE_NAME_PATH
```

Referencias: https://github.com/tvheadend/tvheadend/blob/8837853a6/src/input/mpegts/iptv/iptv_auto.c ; https://github.com/tvheadend/tvheadend/blob/8837853a6/src/input/mpegts/mpegts_mux.c ; https://github.com/tvheadend/tvheadend/blob/8837853a6/src/channels.c ; https://github.com/tvheadend/tvheadend/blob/8837853a6/src/htsp_server.c ; https://github.com/tvheadend/tvheadend/blob/8837853a6/src/bouquet.c
