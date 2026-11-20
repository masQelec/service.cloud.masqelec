# G3-J — Respaldo privado y búsqueda de referencias

Fecha: 2026-11-21. Rama: develop. **Sin borrado autorizado.**

## Evidencia previa

G3-I en master: `ES - NBA` UUID `3e6be21d508c4effb8de6195294739b9` ausente de la M3U, cero canales asociados, visible en Kodi. `PRECHECK=PASS`, `OWNERSHIP_VERIFIED=NO`, `ROLLBACK_VERIFIED=NO`.

## Implementación

`tools/pvr_g3j_tag_backup_preflight.py`:
- Lee el archivo exacto `/storage/.kodi/userdata/addon_data/service.tvheadend43/channel/tag/<UUID>`, ruta recogida de `update_pvr.py` de `develop`.
- Comprueba fichero regular, tamaño acotado, JSON, nombre y `internal=False`. Rechaza enlace simbólico como origen.
- Escribe **solo una copia privada local** en `/storage/.cache/masqelec-g3-backup`, con nombre exclusivo y modo 0600. Verifica igualdad byte a byte y muestra SHA-256. **No enviar esta copia al chat ni subirla a GitHub**.
- Explora de modo acotado los ficheros de configuración TVH bajo `service.tvheadend43`, buscando referencias textuales al UUID; informa solo contadores, no rutas ni datos privados. El barrido es una heurística y no prueba ausencia global de referencias (DVR/EPG/cache y estructura binaria pueden tener relaciones no visibles).
- Nunca hace POST, DELETE ni manipula la configuración TVH original. No toca Kodi, SQLite, M3U ni EPG.
- Siempre muestra `OWNERSHIP_VERIFIED=NO`, `UUID_RESTORE_PROVEN=NO`, `DELETE_AUTHORIZED=NO`.

Tests `tests/test_pvr_g3j_tag_backup_preflight.py` (7 casos) con fixtures en directorios temporales.

## Ejecutar en Ubuntu (tests)

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3j_tag_backup_preflight.py' -v
```

## Ejecutar en master (preflight real)

```bash
scp service.cloud.masqelec/tools/pvr_g3j_tag_backup_preflight.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3j_tag_backup_preflight.py'
```

Si la ruta real difiere o el script bloquea, **no mover ni editar ficheros TVH para forzar la prueba**. Revisar datos primero.

## Gates todavía pendientes

- Corroborar propiedad del grupo por el addon y comprobar vínculos con DVR y otros componentes (no solo `channel/grid`).
- Demostrar restauración del mismo objeto con su UUID original. Una creación temporal con UUID distinto no basta.
- Plan de rollback con Tvheadend, sin reintroducir silenciosamente un tag UUID distinto, y verificación en Kodi.
- Borrado único del histórico solo tras autorización expresa del operador y snapshot adecuado.
- Mecanismo de refresco inmediato de M3U aún sin demostrar.
- No integrar eliminación ni reescritura de índices en `update_pvr.py`; no publicar ZIP.
