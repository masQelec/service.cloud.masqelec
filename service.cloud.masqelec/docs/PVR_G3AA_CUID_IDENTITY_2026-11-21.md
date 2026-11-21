# G3-AA — identidad CUID offline y preparación del ensayo de persistencia (2026-11-21)

## Evidencia del formato real

Se inspeccionó por API GitHub **sin publicar URLs ni claves** `masQelec/cloud.masqelec/pvr/playlist.m3u` en la rama predeterminada. En el momento de la consulta contiene **865** entradas `#EXTINF`; las 865 incluyen el atributo **`CUID="..."`** y sus 865 valores son únicos. También aparecen `tvg-chno`, `tvg-name`, `tvg-logo` y `group-title` en esas entradas.

**Diferencia crítica de estado:** el inventario anterior del master incluía **720 canales**, mientras el fichero remoto actual contiene **865 entradas**. Estos recuentos son de sistemas/momentos distintos: no afirmar divergencia de producción sin confirmar fecha de sincronización, filtro y procedencia de la M3U del master. No aplicar esta playlist al laboratorio ni producción automáticamente.

La M3U sintética original G3-W no incluía CUID; por ello no valida identidad CUID entre TVH y Kodi. El resultado G3-Z5 muestra que un servicio inactivo sin canal puede compartir multiplexor con uno usado por un canal: no borrar mux/servicios por conteo.

## Cambio realizado

Se añade `lib/pvr_cuid_offline.py` como biblioteca sin I/O por defecto:
- `parse(content)`: lee M3U `#EXTM3U`, `#EXTINF`, CUID entrecomillado, tvg-name, group-title y URL; bloquea CUID ausente, duplicado o vacío, playlist truncada, URL ausente e inventarios vacíos. Acepta valores CUID como cadena opaca (no supone que tengan formato UUID).
- `compare(before,after)`: compara **solo por CUID**. Produce conteos de identidades retenidas, añadidas y retiradas, cambios de nombre, URL, grupo y posición, y recuentos de nombres homónimos. No imprime CUID ni valores de URL, ni habilita borrado.
- `load(path)`: lectura local para futuras pruebas, con bloqueo ante enlaces simbólicos, ausencia o fichero excesivo.
- Declaraciones siempre falsas: `tvh_preserves_cuid_proven`, `kodi_preserves_cuid_proven`, `delete_authorized`.

`tests/test_pvr_cuid_offline.py` incluye **15 pruebas sintéticas**, sin Docker/Kodi, de identidad ante renombrado, URL nueva, cambio de grupo, orden invertido, nombres idénticos con CUID diferentes, altas/bajas y malformaciones. **Las pruebas están pendientes de ejecución en Ubuntu**. No se ha modificado `update_pvr.py` en esta fase.

## Ejecutar pruebas (solo desarrollo Ubuntu)

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/lib/pvr_cuid_offline.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_cuid_offline.py' -v
```

## Próximos gates

1. Construir un **segundo laboratorio sintético**, separado de las 2/3 entradas G3-W históricas, con `CUID` estable, cambios deliberados y nombres duplicados. No sobrescribir el fixture G3-W usado para baselines previos.
2. Capturar UUID TVH, referencias de servicios, Kodi channelid y etiquetas por etapas; comprobar cuándo Tvheadend conserva o regenera UUID al cambiar nombre, URL, grupo y orden.
3. Distinguir expresamente correlación por cambios controlados de verdadera preservación del CUID por TVH. El hecho de que M3U contenga CUID **no implica** que TVH lo utilice internamente.
4. Confirmar qué atributos del formato M3U reconoce Tvheadend (no asumir que `CUID` tiene significado para él). Si no transporta CUID hasta el backend, el plan puede requerir una tabla local de correspondencia construida y validada por ingestión, no deducida de nombres.
5. Mantener `G3AA_CUTOVER_AUTHORIZED=NO`, sin tocar SQLite, TVH/Kodi master ni tags históricos.


## Validación de pruebas offline — operador, 2026-11-21

El operador comunicó la salida de `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_cuid_offline.py' -v`:

```text
----------------------------------------------------------------------
Ran 15 tests in 0.002s

OK
```

`G3AA_OFFLINE_UNIT=PASS_15_OF_15`. Es una validación de la comparación CUID en memoria, no una prueba de persistencia de identidad TVH/Kodi. `G3AA_TVH_CUID_PERSISTENCE=NOT_TESTED`, `G3AA_KODI_CUID_PERSISTENCE=NOT_TESTED`, `G3AA_CUTOVER_AUTHORIZED=NO`. Siguiente gate: fixture separado para cambios reales de metadatos con snapshots de IDs entre etapas, evitando alterar G3-W original ni las listas de producción.
