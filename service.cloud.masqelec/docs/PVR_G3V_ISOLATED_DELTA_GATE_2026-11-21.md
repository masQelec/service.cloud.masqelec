# G3-V — Gate funcional 2→3→2 en laboratorio aislado

Fecha: 2026-11-21. Rama: `develop`. Sin despliegues.

## Objetivo

Demostrar que **una baja efectiva** de un canal en TVH se propaga hasta Kodi, conservando los IDs de los canales existentes. Los inventarios del master ya coincidieron descriptivamente (TVH 720, Kodi 720), pero eso **NO** demuestra el comportamiento ante una baja.

## Entregables de este bloque

- `tools/pvr_g3v_isolated_delta_gate.py`: validador **offline** de un informe JSON de tres observaciones `before`, `added` y `removed`. Exige que TVH y Kodi estén en 2→3→2 canales, que el nuevo canal tenga ID único y desaparezca de ambos tras su baja, y que los dos canales originales mantengan ID y nombre en cada sistema. Bloquea si falta evidencia declarada de re-fetch, aislamiento completo, conexión exclusiva Kodi→TVH de laboratorio o no modificación de producción.
- `tests/test_pvr_g3v_isolated_delta_gate.py`: 10 tests con fixtures sintéticos; comprueba coincidencia, delta incompleto, huérfanos Kodi, recreación de IDs, nombres modificados, IDs duplicados y barreras de aislamiento.

**Limitación explícita:** el validador examina un informe suministrado por el operador. Los flags `lab_isolated`, `tvh_refetch_observed`, `kodi_connected_only_to_lab_tvh` y `production_untouched` son **declaraciones de procedencia**, no verificaciones independientes de un servidor real. Ninguna prueba sintética habilita el corte por sí sola. No declara identidad CUID entre sistemas.

## Entorno necesario para el ensayo real

- Instancia de Tvheadend de laboratorio **separada**, con configuración y puerto propios, no la red `IPTV LOCAL` del master (`9981`).
- M3U de laboratorio local con dos canales de prueba inicialmente y un tercero añadido después. URLs de stream **de prueba**, sin credenciales de clientes.
- Instancia Kodi de laboratorio con perfil/base de datos propios, cliente PVR conectado **solo** a TVH de laboratorio; no tocar `/storage/.kodi/userdata/Database/TVxx.db`.
- Tres capturas desde APIs de las instancias de laboratorio: `before` 2/2, `added` 3/3 y `removed` 2/2. El número por sí solo no basta; registrar ID interno y nombre de cada canal.
- Confirmar evidencia efectiva de la relectura TVH; esperar su intervalo configurado no demuestra por sí solo el evento de refetch.
- No reutilizar ni editar `/storage/.user/playlist.m3u` de producción ni conectar Kodi real de la familia al TVH de laboratorio.

Ejemplo de **estructura**, no evidencia real:

```json
{
  "schema": 1,
  "lab_isolated": true,
  "kodi_connected_only_to_lab_tvh": true,
  "production_untouched": true,
  "stages": {
    "before": {"tvh_refetch_observed": true, "tvh": [{"id":"t1","name":"Uno"},{"id":"t2","name":"Dos"}], "kodi": [{"id":"k1","name":"Uno"},{"id":"k2","name":"Dos"}]},
    "added": {"tvh_refetch_observed": true, "tvh": [{"id":"t1","name":"Uno"},{"id":"t2","name":"Dos"},{"id":"t3","name":"Tres"}], "kodi": [{"id":"k1","name":"Uno"},{"id":"k2","name":"Dos"},{"id":"k3","name":"Tres"}]},
    "removed": {"tvh_refetch_observed": true, "tvh": [{"id":"t1","name":"Uno"},{"id":"t2","name":"Dos"}], "kodi": [{"id":"k1","name":"Uno"},{"id":"k2","name":"Dos"}]}
  }
}
```

**No marcar estos flags true basándose solo en los tests ni copiar este ejemplo como si fuera una observación real.** Los IDs reales serán los devueltos por los respectivos servicios de laboratorio.

## Validación de tests (Ubuntu)

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3v_isolated_delta_gate.py' -v
```

Esperados **10 tests**. No declarar PASS hasta recibir ejecución del operador.

Uso del evaluador después de conseguir observaciones **reales aisladas**:

```bash
python3 service.cloud.masqelec/tools/pvr_g3v_isolated_delta_gate.py /ruta/privada/informe_g3v_lab.json
```

No ejecutar este evaluador sobre un reporte fabricado para justificar cambios de producción.

## Resultados posibles y decisión

- **`LAB_DELTA=PASS` sobre observaciones reales y verificables:** autoriza estudiar el siguiente paso de integración (NO autoriza por sí solo suprimir el fallback antiguo ni merge de funcionalidad).
- **Kodi mantiene el tercero tras TVH volver a dos:** `KODI_REMOVE=FAIL` / `G3V=BLOCKED`; conservar vía de limpieza segura y no declarar sincronización nativa funcional.
- **Los canales preexistentes cambian de identidad:** bloqueo, incluso si los números coinciden.
- **Instancias no aisladas o evidencias ausentes:** no ejecutar mutaciones; estado `DEFERRED`.

## Situación del master

M3U 720, TVH 720, Kodi 720, 26 grupos deseados y 6 tags históricos preservados. No se ha ejecutado delta 2→3→2 en master, ni demostrado supresión nativa de huérfanos. `update_pvr.py` sigue con soft reset/SQLite/ficheros históricos: no hacer corte a producción antes de un sustituto probado. La publicación ZIP es responsabilidad del operador.

**Estado:** `G3V_OFFLINE_GATE_IMPLEMENTED=YES`; `G3V_REAL_LAB_DELTA=NOT_EXECUTED`; `LEGACY_REPLACED=NO`; `MASTER_TOUCHED=NO`.
