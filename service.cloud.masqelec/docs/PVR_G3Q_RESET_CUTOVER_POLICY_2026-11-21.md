# G3-Q — Política de corte sin reset, gate de solo diagnóstico

Fecha: 2026-11-21. Rama: develop.

## Inspección precisa del código activo

En `lib/update_pvr.py::update_playlist`, después de descargar la plantilla y sustituir credenciales se compara el hash final de la M3U. Por separado, `_plan_reconcile` analiza la base Kodi `TVxx.db`; una discrepancia puede activar `needs_soft_reset` aunque la M3U no haya cambiado.

Si `needs_soft_reset=True`, el código heredado deshabilita pvr.hts, limpia canales TVH, detiene TVH, instala M3U, reconcilia directamente TVxx.db y sincroniza tags **editando archivos TVH con el servidor detenido**, antes de arrancar TVH y ejecutar otras tareas EPG/PVR. Esto todavía no se ha sustituido y sigue siendo potencialmente disruptivo.

El shadow G3-P solo se ejecutaba después del arranque de TVH, por tanto en el camino `needs_soft_reset=False` no se ejecutaba.

## G3-Q implementado

- `lib/pvr_update_policy.py`: clasificador puro de decisión. Considera `playlist_changed`, `db_mismatch` y evidencias adicionales de READY TVH, refetch real, identidad de canales, asociación de grupos y convergencia en Kodi.
- Cualquier cambio o discrepancia exige seguir con la política heredada **hasta** demostrar las cinco garantías. Incluso si todas se indican como verdaderas, el módulo no habilita el corte automático: requiere revisión manual y otra fase de integración.
- `lib/update_pvr.py`: añade `[pvr][G3Q][decision]` **antes** de `if not needs_soft_reset:`, por lo que registra tanto la rama sin cambios como la rama que exige reset. Solo registra estado y booleanos; nunca URLs, credenciales ni líneas M3U.
- La clasificación no cambia `needs_soft_reset`, ni redirecciona flujo, ni ejecuta operaciones de escritura. La nueva reconciliación API de G3-L/O continúa desconectada.
- `tests/test_pvr_g3q_update_policy.py`: 12 pruebas sobre los casos con/sin cambios, falta de evidencias, entradas inválidas, y ausencia de autorización automática.

## Verificación local agrupada

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3q_update_policy.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3p_tag_shadow.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3o_tag_cycle.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3n_registry_adapter.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_reconcile.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_plan.py' -v
```

Se esperan **70 pruebas** (12 nuevas y 58 previamente confirmadas por el operador). No declarar PASS de G3-Q hasta ejecución real.

## Para el corte real, siguiente gate G3-R

1. Validar el mecanismo nativo **exacto** de relectura M3U de TVH sin reiniciar el servicio. El valor `refetch_period` está expresado en minutos; no asumir que `mpegts/network/scan` fuerza relectura de fichero.
2. En un entorno aislado o ensayo controlado, verificar deltas 720→865→720 con M3U, UUID/cuid, tags y asociaciones canal-grupo, más PVR Kodi, conservando contenido STRM y grabaciones.
3. Cuando la convergencia sea demostrable, implementar una vía **separada** que instale la playlist de forma atómica y espere a TVH/Kodi, sin tocar TVxx.db ni parar servicios, y un fallback explícito y verificado en fallo.
4. Desactivar el sincronizador viejo de ficheros antes de activar API. La persistencia de UUID del orquestador es requisito para borrar tags propios; seis categorías históricas no son propias por defecto.
5. Ejecutar CI y PR develop→main después del ensayo. El operador publica ZIP. No desplegar el `update_pvr.py` modificado al master todavía.

## Estado

`G3Q_NEW_RESET_FREE_PATH_ACTIVE=NO`
`G3Q_LEGACY_RESET_BEHAVIOR_CHANGED=NO`
`G3Q_AUTO_DELETE_HISTORIC_TAGS=NO`
`G3Q_KODI_SQLITE_WRITES_IN_LEGACY_CODE=YES`
`G3Q_PRODUCTION_DEPLOY=NO`
