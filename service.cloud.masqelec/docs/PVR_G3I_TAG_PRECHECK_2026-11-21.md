# G3-I — Preflight para una categoría histórica, sin borrado

Fecha: 2026-11-21. Rama `develop`.

## Antecedentes

- G3-F integrado: 720/720 canales de M3U/TVH con asociaciones de grupo coherentes en la instantánea actual, sin identidad técnica CUID probada.
- G3-G: 3/3 tests OK; JSON-RPC Kodi encuentra las 26 categorías nuevas, pero devuelve orden alfabético.
- G3-H: el operador confirma visualmente que Kodi presenta primero los 26 grupos ocupados por orden alfabético y después los 6 históricos vacíos, también por orden alfabético.
- API de TVH probada en tags **temporales**, tanto creación, `idnode/save` de índice como eliminación y restauración del inventario.

## Nuevo comprobador

`tools/pvr_g3i_tag_delete_precheck.py`: programa de solo lectura para un candidato concreto **ES - NBA**, UUID `3e6be21d508c4effb8de6195294739b9`. El nombre y UUID son datos del inventario histórico ya confirmado; no identifica ni modifica grupos mediante aproximaciones.

Verifica:
- Grupo ausente de los `group-title` de la M3U instalada.
- Coincidencia única de nombre y UUID en el inventario TVH; `internal=False`.
- Ninguna entrada de `channel/grid` referencia el UUID y todos los canales exponen sus etiquetas.
- El grupo aparece exactamente una vez en el inventario de grupos Kodi por JSON-RPC.
- M3U y TVH tienen recuentos iguales y la definición del tag puede consultarse por `idnode/load` GET (sin imprimirla).
- No se realiza ninguna llamada de escritura a Tvheadend ni Kodi. No se accede a `TVxx.db`.

Una salida `PRECHECK=PASS` **no autoriza** borrado: el programa siempre emite `OWNERSHIP_VERIFIED=NO`, `ROLLBACK_VERIFIED=NO` y `DELETE_AUTHORIZED=NO`.

## Pruebas

`tests/test_pvr_g3i_tag_delete_precheck.py`: 9 tests unitarios nuevos sobre coincidencias, canales ocupados, categorías internas, ausencia en Kodi, duplicados y bloqueo de endpoints no permitidos. Ejecución aún pendiente por el operador.

## Ejecución

Desde Ubuntu:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3i_tag_delete_precheck.py' -v
scp service.cloud.masqelec/tools/pvr_g3i_tag_delete_precheck.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3i_tag_delete_precheck.py'
```

## Próximas salvaguardas antes de borrar una etiqueta histórica

1. **Propiedad:** acreditar que el grupo se creó y administró por la sincronización histórica del addon (por código/ruta de datos respaldados y, de ser posible, trazas). Un grupo vacío del TVH no basta.
2. **Protección integral:** comprobar otros usos, grabaciones/reglas y cualquier configuración de TVH que referencie el grupo; `channel/grid` solamente acredita la ausencia de asociaciones de canal observadas.
3. **Backup recuperable:** exportar configuración exacta y verificar el método de restauración con un tag temporal antes de borrar objetos originales.
4. **Borrado piloto explícito y acotado:** una sola etiqueta por UUID mediante API, tras autorización del operador, con postcheck en TVH y Kodi sin resetear SQLite.
5. **Sin automatización destructiva** ni modificaciones en `update_pvr.py` hasta que el piloto y la recuperación estén validados.


## Ejecución real del preflight (operador, 21-11-2026)

Resultado de solo lectura en el master `192.168.1.102`:

```text
M3U_CHANNELS=720
TVH_CHANNELS=720
TVH_TAGS=32
TARGET_PRESENT_IN_M3U=FALSE
TARGET_TAG_MATCHES=1
TARGET_NAME_MATCHES=1
TARGET_TVH_LINKED_CHANNELS=0
TARGET_KODI_GROUP_MATCHES=1
CHANNEL_ROWS_WITHOUT_TAGS_LIST=0
PRECHECK=PASS
OWNERSHIP_VERIFIED=NO
ROLLBACK_VERIFIED=NO
DELETE_AUTHORIZED=NO
```

**Interpretación:** `ES - NBA` está ausente en la M3U actual, su UUID y nombre son inequívocos, no tiene referencias entre los canales de la cuadrícula observada, pero permanece visible en Kodi. Es una **candidata** a limpieza, no un borrado autorizado. El preflight no inspecciona exhaustivamente DVR, bouquets ni referencias en otras configuraciones.

**Próximo gate G3-J:** copia de seguridad exacta y confidencial del tag, inspección de referencias adicionales, ensayo de creación/restauración de un tag temporal por API y verificación de reversibilidad. El borrado piloto del tag histórico solo podrá proponerse después de acreditar pertenencia y recuperación. No tocar `TVxx.db`, M3U ni EPG.
