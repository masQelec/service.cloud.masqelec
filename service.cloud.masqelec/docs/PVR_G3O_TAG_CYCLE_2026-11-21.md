# G3-O — Orquestación segura de categorías (aislada)

Fecha 2026-11-21. Rama develop.

## Hallazgo clave en el flujo existente

En `lib/update_pvr.py`, el mantenimiento actual llama a `sync_tvh_channel_tags_from_playlist(playlist_file)` mientras Tvheadend está **parado**, y luego arranca el servicio. El sincronizador antiguo modifica directamente `channel/tag` y puede eliminar etiquetas ajenas. **No es correcto sustituir esa llamada en el mismo punto por el reconciliador de API HTTP**, porque allí la API TVH no está disponible.

La activación se diseñará como una fase posterior a `_start_tvheadend()` y `_wait_tvheadend_ready()`, suprimiendo previamente la llamada de ficheros. No se ha realizado ese cambio en este bloque.

## Código añadido

`lib/pvr_tag_cycle.py` implementa `run_cycle(playlist, read_snapshot, post, private_dir, *, apply=False, allow_delete=False)`:
- Directorio privado preexistente, registro UUID persistente G3-N y bloqueo entre procesos con `flock`.
- **Diagnóstico por defecto**: `apply=False` no llama API de escritura.
- En modo aplicación, un máximo de **una** mutación: primero altas que falten, después bajas explícitas de UUID propios vacíos y ausentes de la M3U.
- Antes de la mutación escribe `pending-tvhtag.json` con O_EXCL, modo 0600 y fsync. Si el proceso se interrumpe antes de confirmar y persistir la respuesta, el diario queda y **bloquea futuras operaciones**. No se adopta silenciosamente el objeto que pudo crear TVH en una pérdida de respuesta.
- Tras confirmar la mutación, persiste atómicamente el registro UUID y solo entonces retira el diario; si persiste un diario, se necesita revisión manual.
- El contenido del diario solo contiene operación/identificador de etiqueta. No contiene URLs ni credenciales.
- Reutiliza `pvr_tag_reconcile.py` y `pvr_tag_plan.py`, ambos sujetos a las barreras de inventario estable.
- Ni SQLite Kodi, ni M3U, ni EPG, ni archivos `channel/tag` se alteran desde este módulo.

## Pruebas añadidas

`tests/test_pvr_g3o_tag_cycle.py`: 10 pruebas con TVH simulado, archivos privados temporales y cero llamadas de red. Cubren dry run, alta con persistencia, segunda ejecución sin cambios, conservación de tags ajenos, caída tras API, diario pendiente, registro corrupto, baja de tag propio, protección de tag ocupado y permisos de directorio.

## Ejecutar en Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3o_tag_cycle.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3n_registry_adapter.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_reconcile.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_plan.py' -v
```

Esperados: 10 + 15 + 13 + 13 = **51 tests**. El operador debe aportar resultado; no se declara PASS hasta entonces.

## Pendientes para cierre G3-O / despliegue

1. Conectar correctamente el adaptador autenticado de G3-N después del inicio/READY de TVH en `update_pvr.py` y suprimir el sincronizador antiguo. No ejecutar ambos nunca.
2. Mantener `allow_delete=False` y protección de las seis categorías históricas, sin atribuirles propiedad por estar vacías.
3. Confirmar que la creación de grupo ausente conduce a enlaces canal-grupo correctos tras refetch de la M3U. La creación API no hace ese enlace por sí sola, y el planificador actual verifica recuentos y no todos los pares esperados por grupo.
4. Ensayar reinicio/pérdida de respuesta: diario pendiente debe impedir reintento destructivo o adopción implícita. Documentar recuperación manual después de accidente.
5. Confirmar impacto y actualización en Kodi por medios nativos, sin escribir en TVxx.db.
6. Ejecutar suite completa/CI/PR antes de habilitar. Publicación ZIP exclusiva del operador.

**Estado:** orquestador aislado en develop, ejecución real no autorizada, producción intacta. La validación de G3-M real (720 canales, 26 grupos M3U, 32 tags TVH, 6 vacíos históricos) permanece como referencia.


## Resultado de ejecución de tests — confirmado por el operador

Tras sincronizar `develop`, el operador confirma que las cuatro baterías terminaron en `OK`:

- `test_pvr_g3o_tag_cycle.py`: 10/10
- `test_pvr_g3n_registry_adapter.py`: 15/15
- `test_pvr_tag_reconcile.py`: 13/13
- `test_pvr_tag_plan.py`: 13/13
- **Total G3-O: 51/51 OK.**

Resultado **unitario**, no equivale a integración funcional real ni a autorización para eliminar los grupos históricos. El orquestador no está conectado al ciclo de `update_pvr.py`; el método antiguo de modificación directa de archivos de tags sigue en la base de código.

**Siguiente gate G3-P:** sustituir el sincronizador viejo por una única entrada API post-READY, con protección frente a doble ejecución; empezar en modo lectura y `allow_delete=False`, y validar convergencia de asociaciones canal-grupo en Tvheadend y Kodi antes de permitir escrituras reales. No publicar ZIP ni cambiar M3U/EPG/SQLite.
