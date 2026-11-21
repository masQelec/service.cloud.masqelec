# G3-R — Re-fetch de IPTV LOCAL: fuente, límites y prueba de lectura

Fecha 2026-11-21; rama develop. Producción sin cambios.

## Investigación del upstream

En el código de Tvheadend `src/input/mpegts/iptv/iptv.c`, clase `iptv_auto_network_class`, el atributo `refetch_period` se denomina «Re-fetch period (mins)» y tiene valor por defecto `60`. La propiedad `url` utiliza `iptv_auto_network_class_url_set` y un notify que llama a `iptv_auto_network_trigger(in)`. Fuentes:
- https://github.com/tvheadend/tvheadend/blob/master/src/input/mpegts/iptv/iptv.c
- https://old.tvheadend.org/projects/tvheadend/wiki/Automatic_IPTV_Network

**Importante:** la presencia del trigger de cambios URL en upstream no demuestra que guardar el mismo valor por API en la versión instalada lo dispare. Tampoco justifica alterar temporalmente la URL a una ruta inexistente como estrategia de producción.

En discusiones sobre la API se describe que un rescan puede revisar los muxes existentes sin releer el fichero M3U. No confundir `mpegts/network/scan` con fuerza de refetch:
- https://tvheadend.org/d/5952-force-reload-of-iptv-network
- https://tvheadend.org/d/8727-ability-to-reload-channel-lists-in-the-gui-and-via-script

## Entrega G3-R

`tools/pvr_g3r_tvh_refetch_readonly.py` consulta solo GET:
- `mpegts/network/grid` e `idnode/load` para el UUID conocido de IPTV LOCAL `cce41e6f2d9b5d829d3af38159eea0a5`;
- verifica que la ruta M3U local existe y que, si TVH expone el campo, la URL coincide con `file:///storage/.user/playlist.m3u`;
- comunica el período de re-fetch **en minutos** sin imprimir la URL ni credenciales;
- exige que el inventario de red no sea parcial y que el objeto sea único.
- Si esta versión TVH no expone `props` como lista de `id`/`value`, bloquea con `NETWORK_PROPERTIES_UNAVAILABLE` para adaptar el lector a un ejemplo estructural **redactado**. No inferir un valor ausente.

`tests/test_pvr_g3r_tvh_refetch_readonly.py`: 5 tests simulados: red local correcta, URL no esperada sin exposición, periodo ausente, red duplicada y bloqueo de endpoints de escritura.

## Ejecutar en Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3r_tvh_refetch_readonly.py' -v
```

## Enviar al master sin alterar producción

```bash
scp service.cloud.masqelec/tools/pvr_g3r_tvh_refetch_readonly.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3r_tvh_refetch_readonly.py'
```

Salida limitada a banderas/contadores y sin contenido de la M3U.

## Gate posterior

Verificar de forma controlada el comportamiento en la **versión de Tvheadend instalada**, idealmente sin modificar el listado real: primero contraste del período y logs de re-fetch natural; después ensayos con lista y red temporal aisladas, si es viable. Comprobar convergencia de canales, nombres, iconos, grupos, vínculos y Kodi antes de sustituir `update_pvr.py`.

**Sin confirmación de trigger inmediato, mantener refetch periódico natural y no activar el corte sin reset.**

`TVH_URL_CHANGED=NO`, `REFETCH_PERIOD_CHANGED=NO`, `NETWORK_SCAN_EXECUTED=NO`, `KODI_DB_TOUCHED=NO`, `LEGACY_CUTOVER_AUTHORIZED=NO`, `ZIP_PUBLISHED=NO`.
