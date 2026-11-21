# G3-Y — Inventario de campos de identidad (21/11/2026)

## Diagnóstico de las evidencias existentes

- G3-W: Tvheadend y Kodi Ubuntu realizaron **2→3→2** sin modificar DB SQLite y conservaron los UUID/IDs originales. Esto prueba convergencia del caso simple.
- Las pruebas G3-X del operador: **16 tests PASS**, de la función pura `pvr_native_convergence.classify`; no validan la integración por API.
- La M3U sintética G3-W, según el código real `lab/pvr_g3w/prepare.py`, escribe `tvh-chnum`, `tvg-chno`, `group-title`, nombre y URL, **pero no incluye CUID**. Por ello G3-W no prueba preservación de CUID.
- Kodi JSON-RPC `PVR.GetChannels` confirmó `channelid=1,2,3`, pero `channelid` es una identidad de la vista Kodi y por sí solo no revela el UUID del canal backend TVH. El TVH `channel/grid` devuelve UUID; no se ha demostrado aún relación inequívoca entre ambos.
- Las 24 ocurrencias de nombres duplicados del inventario real del master hacen imprescindible verificar correspondencia a nivel de backend. No admitir nombres como identidad.

## Nueva herramienta de solo lectura

`tools/pvr_g3y_identity_fields_lab.py` hace **exclusivamente**:
1. HTTP GET `http://127.0.0.1:19981/api/channel/grid?start=0&limit=20000`;
2. JSON-RPC `PVR.GetChannels` en `http://127.0.0.1:8080/jsonrpc`, vía POST de lectura, con paginación explícita;
3. exige total completo y respuestas válidas; ante error devuelve `G3Y=BLOCKED`;
4. imprime conteos, nombres de campos disponibles en todas las filas y tipos de campos relevantes. No muestra nombres de canales, URL, credenciales ni valores de UUID;
5. declara siempre `CUID_TO_TVH_UUID_PROVEN=NO`, `TVH_UUID_TO_KODI_CHANNELID_PROVEN=NO`, `IDENTITY_DELETION_AUTHORIZED=NO`, `SQLITE_TOUCHED=NO`.

Endpoints permitidos rígidamente: **solo loopback del laboratorio Ubuntu**, `19981` y `8080`. No usarlo en CoreELEC; no accesos destructivos. No se permite contraseña por argumentos CLI para evitar filtración en listado de procesos. Si Kodi exige autenticación HTTP, la herramienta debe bloquear y se incorporará un transporte seguro por separado.

## Pruebas preparadas

`tests/test_pvr_g3y_identity_fields_lab.py`: 12 casos sintéticos (no exponen secretos, no equiparan IDs, paginación incompleta, tipos, endpoints fuera de laboratorio). No se declara PASS hasta que el operador los ejecute.

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/tools/pvr_g3y_identity_fields_lab.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3y_identity_fields_lab.py' -v
python3 service.cloud.masqelec/tools/pvr_g3y_identity_fields_lab.py
```

Debe seguir arrancado el Kodi del laboratorio, con el servidor JSON-RPC local accesible y TVH de laboratorio en el puerto 19981. La playlist ahora está en etapa `removed` (2 canales), suficiente para este inventario de campos.

## Próximas comprobaciones

A. Inspeccionar la estructura de los campos `services` y la identidad subyacente del servicio IPTV de TVH, sin publicar ni depender de URLs privadas. B. Determinar si Kodi expone `iUniqueId` y el vínculo de backend a través de una API de solo lectura o un snapshot SQLite **aislado y solo lectura** en Ubuntu; la presencia de `channelid` no basta. C. Para probar CUID, preparar **otro** fixture con CUID estable y los cambios de nombres/números deliberados, no inventar que el fixture antiguo tenía CUID. D. Si no existe correspondencia demostrable, conservar el bloqueo y diseñar reconciliación por identidad desde la propia cadena de ingestión, no usar eliminación SQL a ciegas.

## Cambios excluidos

Sin modificaciones en `update_pvr.py` durante G3-Y, sin cambios en master, sin deploy, sin gestión de tags históricos, sin eliminación de canales, sin llamada a APIs mutadoras.
