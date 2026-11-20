# G3-G — Orden Kodi y refresco TVH (solo lectura)

Fecha: 2026-11-21. Rama: `develop`. Sin cambios en addon activo, playlist, SQLite, Tvheadend ni Kodi.

## Hechos verificados

- G3-F LIVE master: M3U 720, Tvheadend 720, parejas por nombre exacto 696, parejas nombre/número 24, divergencias de grupo 0, autorizaciones de escritura NO.
- Tvheadend `iptv_auto_network`: `refetch_period` en **minutos**, valor predeterminado **60** en el código fuente upstream `src/input/mpegts/iptv/iptv.c`; el operador configuró temporalmente 1.
- Kodi documenta `PVR.GetChannelGroups` (JSON-RPC ReadData) y una opción de orden de grupos procedente de backend.
- Todavía **no** está probado que `mpegts/network/scan` provoque una relectura de la M3U; no utilizarlo como disparador automático.

## Implementación

- `tools/pvr_g3g_kodi_groups_readonly.py`: extrae grupos en orden de la M3U local y realiza `GET` a Tvheadend `channeltag/grid`, `POST` JSON-RPC `PVR.GetChannelGroups` (solo método ReadData) a Kodi `127.0.0.1:8080`. Informa de grupos presentes/ausentes, orden relativo de los que coinciden y muestra los grupos reconocidos, sin URLs IPTV ni credenciales.
- `tests/test_pvr_g3g_kodi_groups_readonly.py`: igualdad/desigualdad de orden y filtro de grupo Kodi sintético.
- `KODI_ORDER_MATCH=YES` solo certifica coincidencia en el orden devuelto por JSON-RPC **de los grupos que han podido reconocerse**. Verificar `KODI_M3U_GROUPS_MISSING=0` y descartar duplicados antes de afirmar coincidencia íntegra.
- En Kodi la función de servidor web debe estar activada para responder a `127.0.0.1:8080/jsonrpc`. Si no está activa, el diagnóstico es `INCONCLUSIVE`; **no habilitarla automáticamente**. Ejecutar el probe en master si Kodi reside allí, no en Ubuntu.

## Prueba agrupada

Ubuntu:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3g_kodi_groups_readonly.py' -v
scp service.cloud.masqelec/tools/pvr_g3g_kodi_groups_readonly.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
```

Master:

```bash
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3g_kodi_groups_readonly.py'
```

La salida permite decidir si se necesita investigar JSON-RPC Kodi o su configuración, y si el orden de grupos requiere un experimento separado. No se llama ninguna API de escritura.

## Gates pendientes

1. Verificar `KODI_ORDER_MATCH` y `KODI_M3U_GROUPS_MISSING`, además de contar otras categorías Kodi no gestionadas.
2. Determinar en la instalación concreta una vía real de refresco M3U instantáneo y demostrarla primero con snapshots, sin reiniciar TVH.
3. Antes de cambiar M3U antigua/nueva, proteger DVR y registrar los 720 canales originales, grupos e índices.
4. Cualquier borrado de las seis categorías antiguas exige verificar propiedad, ausencia de usos y copia de recuperación. La prueba de API temporal no autoriza su borrado.
5. No integrar el aplicador en `update_playlist()` ni tocar Kodi SQLite durante este bloque.
