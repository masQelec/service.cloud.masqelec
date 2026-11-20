# G3-M — Integración de lectura real con TVH (primera puerta)

Rama `develop`. Sin integración en el ciclo activo ni cambios en Kodi/TVH.

## Alcance

`tools/pvr_g3m_tvh_readonly_integration.py` usa la M3U instalada y los endpoints GET `channeltag/grid` y `channel/grid`. Alimenta al planificador `lib/pvr_tag_plan.py`, reconsulta ambos inventarios y rechaza deriva entre lecturas, datos parciales, asociaciones faltantes y desajuste de recuentos.

Salida resumida sin publicar URLs, credenciales, datos de canales ni contenido M3U:
- número de canales/grupos M3U y canales/tags TVH
- faltantes propuestos para creación
- diferencias de índice **solo informativas**, no autorizan reordenamiento
- vacíos históricos preservados por no estar registrados como propiedad
- `API_WRITE_EXECUTED=NO` y `HISTORIC_DELETE_AUTHORIZED=NO`

**Atención:** este diagnóstico no demuestra que crear un grupo vacío asigne automáticamente sus canales ni que TVH vuelva a crear grupos tras un refetch. No prueba idempotencia real del escritor. Las seis categorías antiguas permanecen intactas.

## Validación Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3m_tvh_readonly_integration.py' -v
```

Cinco pruebas simuladas: estado esperado, drift, inventario parcial, límite de endpoints y falta de convergencia.

## Lectura master

```bash
scp service.cloud.masqelec/tools/pvr_g3m_tvh_readonly_integration.py service.cloud.masqelec/lib/pvr_tag_plan.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3m_tvh_readonly_integration.py'
```

Ambos archivos deben ubicarse juntos en el directorio de diagnóstico del master. La ejecución no tiene escrituras.

## Antes de activar el reconciliador en el addon

El sincronizador antiguo en `lib/update_pvr.py` escribe y borra archivos de `channel/tag` directamente. Hay que desactivarlo al incorporar las operaciones API; nunca ejecutar ambos. Falta implementar registro persistente de UUID propios y validar convergencia en TVH/PVR por API con grupo temporal y un canal controlado, sin editar las M3U originales ni asignaciones de canales de producción. Cualquier prueba de creación/borrado temporal requiere gate separado y autorización explícita.

Estado: diseño/pruebas en develop; master y pipeline CI aún pendientes de validación.


## Resultado real master — G3-M (operador)

```text
=== G3-M READ-ONLY TVH INTEGRATION ===
M3U_CHANNELS=720
TVH_CHANNELS=720
M3U_GROUPS=26
TVH_TAGS=32
GROUPS_TO_CREATE=0
GROUPS_TO_REORDER_DIAGNOSTIC=26
OWNED_EMPTY_TO_DELETE=0
UNOWNED_OR_PROTECTED_EMPTY=6
SNAPSHOT_STABLE=YES
API_WRITE_EXECUTED=NO
AUTOMATIC_INTEGRATION_ACTIVE=NO
HISTORIC_DELETE_AUTHORIZED=NO
```

**G3-M lectura real PASS**: inventario estable; todos los grupos de M3U presentes y canales convergidos. `GROUPS_TO_REORDER_DIAGNOSTIC=26` refleja diferencias de índices respecto al orden M3U, **no errores ni permiso para reordenar**. Kodi GUI presenta grupos con canales alfabéticamente y, después, grupos vacíos también alfabéticamente.

Las seis etiquetas históricas están preservadas porque el registro explícito de propiedad aún no las acredita. `OWNED_EMPTY_TO_DELETE=0` es correcto. Ni la prueba demuestra que Tvheadend reconstruya automáticamente asociaciones de canal al recuperar un grupo ni autoriza limpiar históricos.

**Próximo gate**: validar en simulación persistencia atómica del registro de propiedad, creación vía API y comprobación de convergencia tras refetch, antes de integrar con `update_pvr.py`. No mezclar el sincronizador viejo que manipula ficheros con la nueva vía API. Borrado de grupos no autorizados permanece desactivado.
