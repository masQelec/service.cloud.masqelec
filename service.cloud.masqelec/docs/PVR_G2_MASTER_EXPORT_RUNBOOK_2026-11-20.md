# G2 master — captura JSON TVH y contraste offline TV46

**Estado:** herramienta read-only, NO habilita limpieza ni reinicio.

Hallazgo confirmado en la copia `TV46.db` aportada por el operador:
- 865 canales PVR (cliente `pvr.hts`, `iClientId=1`).
- 40 grupos (38 de cliente y 2 internos), 1715 relaciones.
- `idGroup=1` es el grupo real `ES - SEGUNDA FEDERACION`, **no un grupo interno**. Los grupos `Todos los canales` están en IDs 27 y 28, clasificados por `iGroupType=1` e `iClientId=-1`.
- El helper heredado `_is_internal_or_protected_group` protege indebidamente el ID 1: reemplazar el criterio antes de permitir limpieza de grupos, tras ensayo en master.
- `iUniqueId` de Kodi no debe confundirse con `idChannel` SQL, CUID o UUID TVH.

## Cómo obtener el inventario TVH, sin modificarlo

En el **master**, con el navegador ya autorizado en la interfaz web de Tvheadend, consultar la petición **GET** `/api/channel/grid?start=0&limit=20000` y guardar su respuesta JSON localmente como `grid.json`. Verificar que `total` coincide con el número de elementos de `entries`; si hay paginación, no mezclar páginas de momentos distintos. No usar los endpoints de borrado o modificación.

La respuesta JSON sin filtrar puede contener nombres, rutas, enlaces o metadatos privados: **no adjuntarla ni subirla a GitHub**. No subir tampoco credenciales TVH ni URLs de reproducción. Ejecutar el diagnóstico *en el equipo*, contra una copia SQLite consistente ya preparada fuera del árbol `.kodi/userdata`.

```bash
python3 service.cloud.masqelec/tools/pvr_g2_master_diagnostic.py \
    /ruta/aislada/TV46.db /ruta/aislada/grid.json > /ruta/aislada/g2_master_report.json
```

Si el entorno Kodi no permite obtener el export completo por UI, confirmar versión TVH/HTTP/API y preparar un colector independiente con autenticación protegida. **No probar comandos destructivos para obtener datos.**

El informe solo contiene cifras y booleanos; no contiene nombres, URLs ni contraseñas. Es normal que indique `identity_mapping_verified=false` y `orphan_count_verified=null`: las coincidencias exactas por nombre **son indicios, nunca identidad acreditada**. El diagnóstico rechaza esquemas distintos de TV46, archivos live, export incompleto y UUID duplicados.

## Gate pendiente

Para certificar `TVH UUID -> Kodi (iClientId,iUniqueId)` hay que obtener identificadores HTSP desde el master y cotejarlos con los de Kodi en el mismo instante. En el código público de pvr.hts, `GetChannels` expone `channel.GetId()` como PVR UniqueId, pero **no confirma** que los UUID de `channel/grid` permitan reconstruir ese valor. Evitar deducirlo de nombres.

Las pruebas incluidas en `tests/test_pvr_g2_master_diagnostic.py` son sintéticas y nunca acceden a producción.

**G2_DIAGNOSTIC=READY_FOR_OFFLINE_EXPORT**, **G2_CROSSWALK=UNVERIFIED**, **SQLITE_WRITE=BLOCKED**, **EPG_COVERAGE=OPTIONAL**.
