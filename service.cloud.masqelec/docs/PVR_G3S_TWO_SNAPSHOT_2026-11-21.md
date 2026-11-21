# G3-S — Observación de dos inventarios de TVH, solo lectura

Fecha: 2026-11-21. Rama: `develop`.

## Entrada confirmada G3-R

El master TVH responde `idnode/load` con esquema `PARAMS`, URL exacta `file:///storage/.user/playlist.m3u` y `refetch_period=1` minuto temporalmente. G3-R no demostró ejecución del refresco ni convergencia Kodi.

## G3-S implementado

`tools/pvr_g3s_tvh_two_snapshots.py` es autónomo, sin dependencia de módulos del addon. Obtiene dos observaciones separadas por 75 segundos por defecto, exclusivamente por GET HTTP a `channeltag/grid` y `channel/grid` y lectura local de `playlist.m3u`. Compara:
- hash de bytes de M3U, conteo de canales y grupos;
- identidad `uuid→nombre` de tags TVH y pares `uuid→conjunto de tags UUID` de canales;
- inventarios completos y sin UUID/nombres duplicados, canales sin tags, referencias a tags inexistentes;
- presencia de todos los grupos de la M3U en TVH y al menos un canal enlazado por grupo;
- categorías TVH sobrantes solo se cuentan, nunca se borran.

**Limitación clave:** dos snapshots idénticos no prueban un evento real de re-fetch; un programa que no refresque también devolvería capturas estables. Tampoco demuestran el CUID original de M3U, equivalencia por canal de las asociaciones ni convergencia Kodi/EPG. No debe declararse refetch validado ni reset-free autorizado con esta única prueba.

Modo error bloqueado: imprime códigos de causa preaprobados sin nombres de canal, UUID, URL ni contraseñas. No crea archivos en el master, no hace POST, no reinicia nada.

## Prueba local agrupada

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3s_tvh_two_snapshots.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3r_tvh_refetch_readonly.py' -v
```

Esperados: **12 pruebas nuevas G3-S y 8 G3-R = 20**. No afirmar PASS hasta ejecutarlas; los 8 tests G3-R actualizados siguen pendientes de confirmación por el operador.

## Observación del master sin cambios de configuración

```bash
scp service.cloud.masqelec/tools/pvr_g3s_tvh_two_snapshots.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3s_tvh_two_snapshots.py --delay 75'
```

Si `STABLE_TWO_SNAPSHOTS`, representa exclusivamente integridad y estabilidad comparada durante el intervalo. Si `BLOCKED`, registrar `REASON` y no hacer cambios de tags ni fallback.

## Gate posterior

Para confirmar relectura real se necesitará evidencia independiente del instante del refetch en registros o una prueba aislada con una M3U de laboratorio y cambios controlados, sin manipular la M3U real. Para conectar el nuevo sincronizador habrá que comprobar el vínculo entre canal M3U y canal TVH a nivel identificador; el recuento de 720 no basta. Kodi debe evaluarse por JSON-RPC o estado nativo, sin modificar SQLite.

`WRITE_EXECUTED=NO`, `TVH_RESTART=NO`, `REFETCH_EVENT_PROVEN=NO`, `KODI_CONVERGENCE_PROVEN=NO`, `AUTO_TAG_DELETE=NO`, `DEPLOY=NO`.
