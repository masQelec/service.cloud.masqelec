# G3-U — Verificación nativa Kodi/TVH sin modificación de SQLite

Fecha 2026-11-21. Rama develop.

## Propósito real

El objetivo del addon sigue siendo retirar de Kodi canales que Tvheadend ya no tiene. G3-S validó estabilidad TVH (720/720, 26 grupos deseados, seis tags históricos). G3-T validó 720/720 pares nombre/grupo con 24 entradas repetidas descriptivamente (10/10 tests corregidos PASS). **Nada de eso prueba limpieza de huérfanos en Kodi.**

La ruta de mantenimiento heredada en `lib/update_pvr.py` todavía detiene TVH, deshabilita pvr.hts y manipula TVxx.db. No sustituir ni retirar ese fallback solo por conteos TVH estables.

## Entrega

`tools/pvr_g3u_kodi_native_readonly.py`: comparación nativa de TVH `channel/grid` (GET) y Kodi `PVR.GetChannelGroups(channeltype=tv)` + `PVR.GetChannels(channelgroupid=alltv)` (JSON-RPC POST **de lectura**). No ejecuta `VideoLibrary.Clean`, no reconfigura addons, no abre SQLite y no altera canales o grupos.

El informe devuelve conteos de canales TVH/Kodi y discrepancias del multiconjunto de nombres, **sin imprimir nombres ni URLs**. Nombres duplicados se cuentan; no se borran ni se asumen idénticos. El método no demuestra coincidencia individual CUID→TVH UUID→Kodi ID; es un observador inicial de huérfanos, no un plan de borrado.

El script bloquea si falta `alltv`, se obtiene inventario parcial, el método JSON-RPC falla o faltan propiedades mínimas. La forma exacta de respuesta JSON-RPC de esta versión Kodi aún no está verificada; adaptar tras ver un error seguro, no inventar compatibilidad.

`tests/test_pvr_g3u_kodi_native_readonly.py`: **10 tests** para coincidencia, huérfanos, faltantes, duplicados, ambigüedad, nombres no disponibles, grupo alltv, ausencia de alltv, paginación parcial y prohibición de métodos fuera de lectura.

## Validación agrupada en Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3u_kodi_native_readonly.py' -v
```

Se esperan 10 tests. No declararlos PASS sin la salida del operador.

## Comprobación real sin modificaciones en master

```bash
scp service.cloud.masqelec/tools/pvr_g3u_kodi_native_readonly.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3u_kodi_native_readonly.py'
```

Kodi debe tener habilitado su servidor JSON-RPC HTTP local tal como los probes G3-G ya utilizaron; cualquier fallo es `BLOCKED`. Si Kodi tiene otros clientes PVR o canales ajenos a la red IPTV, un delta global no es prueba inequívoca de huérfanos; habría que acotar clientes antes de una limpieza.

## Qué falta para finalizar de forma segura

1. Confirmar con API nativa si el master muestra algún canal huérfano ahora. Con nombres repetidos, `DESCRIPTIVE_MATCH` no acredita identidad individual; `DESCRIPTIVE_MISMATCH` solo es evidencia de discrepancia, no identifica qué fila SQLite borrar.
2. Ensayar un delta 1 canal añadido/retirado en **red y M3U aisladas de laboratorio**, con observación del refresco real de TVH y propagación o no de bajas en Kodi. No modificar la M3U de 720 canales del master.
3. Solo si el paso anterior acredita una alternativa nativa, cambiar `update_pvr.py` para eliminar los reinicios y el escritor de tags viejo. Si Kodi conserva huérfanos, implementar fallback SQLite transaccional, versionado, respaldado y verificado, no borrar por nombre.
4. Ejecutar pruebas/CI y PR develop→main; distribución ZIP exclusiva del operador.

**Estado:** `KODI_NATIVE_READONLY_PREPARED=YES`, `KODI_NATIVE_MASTER_TEST=PENDING`, `SQLITE_WRITES_NEW_CODE=NO`, `LEGACY_CUTOVER=NO`, `PRODUCTION_CHANGED=NO`, `ZIP_PUBLISHED=NO`.
