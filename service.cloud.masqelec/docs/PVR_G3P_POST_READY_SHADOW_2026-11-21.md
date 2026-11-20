# G3-P — Shadow read-only integrado en el flujo (desarrollo)

2026-11-21. Rama: `develop`.

## Hallazgo de auditoría

`lib/update_pvr.py` sigue teniendo un flujo amplio de soft reset que:
1. Deshabilita `pvr.hts`.
2. Ejecuta limpieza de canales en TVH.
3. Detiene TVH.
4. Instala nueva playlist (si cambió).
5. Puede reconciliar directamente la base `TVxx.db` de Kodi.
6. Ejecuta `sync_tvh_channel_tags_from_playlist(playlist_file)`, que escribe/elimina directamente archivos de categorías TVH con el servidor detenido.
7. Arranca TVH, espera READY y completa limpieza, EPG y reactivación PVR.

**Este diseño heredado no ha sido sustituido**: el foco de G3-P es insertar una lectura diagnóstica fiable en el punto apropiado. No debe presentarse como mantenimiento nuevo ya activo ni como eliminación de escrituras Kodi.

## Cambios

- Nuevo `lib/pvr_tag_shadow.py`: lectura solamente de M3U e inventarios TVH mediante las funciones autenticadas del addon y el planificador G3-C. Relee inventarios para detectar deriva, y devuelve únicamente contadores/status sin URLs ni credenciales.
- `lib/update_pvr.py`: hook `[pvr][G3P][shadow]` **después** de `_start_tvheadend()` / `_wait_tvheadend_ready()`, antes de otras tareas post-start. El hook detecta excepciones, registra solo estado y contadores, no cambia el retorno de la actualización, no crea/elimina tags y no toca SQLite.
- `tests/test_pvr_g3p_tag_shadow.py`: siete pruebas simuladas para éxito, inventario incompleto, recuento de canales inconsistente, deriva, M3U inválida, fallo de auth y ausencia de rutas de escritura en el módulo shadow.

## Precaución importante

El hook solo corre si la rutina heredada entra en el flujo de cambio/soft reset. La vía `needs_soft_reset=False` retorna antes y por tanto **no** realiza shadow. No extrapolar el resultado del hook a ciclos sin cambios. La lectura GET añade solicitudes de API y latencia, no mutaciones.

## Validación local agrupada

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3p_tag_shadow.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3o_tag_cycle.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3n_registry_adapter.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_reconcile.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_plan.py' -v
```

**58 pruebas esperadas** (7 nuevas + 51 anteriores). Pendientes de resultado del operador; no afirmar PASS sin ejecución.

## Siguiente gate, G3-Q

Separar el nuevo mantenimiento de categorías del soft-reset heredado:
- `pvr.hts`, TVH y `TVxx.db` no deben reiniciarse ni escribirse para simple cambio de grupos de M3U cuando TVH ha convergido.
- Se debe deshabilitar/eliminar **primero** el sincronizador de archivos de categorías y no habilitar en paralelo la escritura API.
- Ejecutar orquestador/API en punto post-READY, inicialmente con `apply=False` y `allow_delete=False`.
- Validar vía API la asociación real de canales con categorías tras refetch, además de los recuentos.
- Ensayar diagnóstico y fallo entre API write/journal/persistencia antes de permitir escrituras.
- La creación API de un grupo **no garantiza** que TVH vuelva a enlazar los canales; se requiere prueba.
- La supresión de categorías antiguas no administradas por el nuevo registro sigue bloqueada. Sus seis UUID no deben incorporarse de forma implícita.

No se ha desplegado en el master ni publicado ZIP; producción, M3U y EPG sin cambios desde este trabajo de repositorio.


## Resultado confirmado por el operador — G3-P

El operador confirma que las cinco baterías de pruebas ejecutadas en Ubuntu terminaron en `OK`:

- G3-P shadow: **7/7**
- G3-O ciclo: **10/10**
- G3-N adaptador/registro: **15/15**
- Reconciliador: **13/13**
- Planificador: **13/13**
- **Total: 58/58 OK.**

Se considera aprobada la batería unitaria agrupada; no implica aprobación de integración real, despliegue, cambios en Kodi/TVxx.db ni eliminación de categorías históricas. Sigue pendiente G3-Q: desacoplar el mantenimiento de grupos del soft reset heredado, preservar integridad de canales y comprobar el comportamiento con Tvheadend real antes del corte.
