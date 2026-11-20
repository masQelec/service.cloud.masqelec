# G3-F LIVE — Ejecutar auditoría real sin instalar el addon

Estado: código en `develop`, gate de ejecución pendiente. Fecha: 2026-11-21.

## Objetivo

`tools/pvr_group_audit_real.py` usa el módulo original `lib/pvr_group_audit.py` (sin duplicar el algoritmo) y únicamente lee:

- `/storage/.user/playlist.m3u` en CoreELEC
- `http://127.0.0.1:9981/api/channeltag/grid`
- `http://127.0.0.1:9981/api/channel/grid`

No modifica la M3U, TVH, Kodi ni SQLite. No lee URLs de reproducción para compararlas ni las escribe en la salida. Solo muestra contadores y estados; cualquier excepción se redacciona como nombre de tipo de excepción sin traceback/URL.

Los dos archivos deben coexistir en el directorio de prueba del master; el comprobador también se puede ejecutar desde el checkout del repositorio, pero la M3U y TVH locales no existen en el Ubuntu de desarrollo.

## Paso 1 — Ubuntu: actualizar y ejecutar tests

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_group_audit_real.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_group_audit.py' -v
```

## Paso 2 — Transferir solo dos archivos al master

Sustituir `MASTER_IP` por la dirección SSH real de CoreELEC; se debe usar un usuario SSH con acceso al directorio de destino. Ninguna contraseña IPTV debe copiarse al entorno Ubuntu.

```bash
ssh root@MASTER_IP 'mkdir -p /storage/.cache/masqelec-g3-audit'
scp service.cloud.masqelec/tools/pvr_group_audit_real.py \
    service.cloud.masqelec/lib/pvr_group_audit.py \
    root@MASTER_IP:/storage/.cache/masqelec-g3-audit/
ssh root@MASTER_IP 'python3 /storage/.cache/masqelec-g3-audit/pvr_group_audit_real.py'
```

Si el master no tiene `python3`, no instalar dependencias ni modificar el sistema sin revisión. El código usa únicamente librerías estándar de Python.

## Salida esperada, no garantizada

```text
RESULT=DIAGNOSTIC_ONLY
M3U_CHANNELS=720
TVH_CHANNELS=720
EXACT_NAME_PAIRS=696
NAME_NUMBER_PAIRS=24
RESOLVED_PAIRS=720
UNRESOLVED=0
GROUP_MISMATCHES=0
READ_ONLY=YES
APPLY_AUTHORIZED=NO
```

En error o inconcluso devuelve código de salida 2. Estado `DIAGNOSTIC_ONLY` significa correspondencia de instantánea por nombre/número y categoría, **no** identidad CUID ni autorización de borrados.

## Gates restantes

- Sincronización de nombres/números de M3U con TVH ya observada en ejecución ad hoc. Pendiente validar contra código instalado real.
- Revisar comportamiento del orden `index` en Kodi sin alterar todas las categorías.
- Refetch de la M3U por API: endpoint real no demostrado.
- Seis categorías vacías: propiedad desconocida, ninguna eliminación autorizada.
- `update_pvr.py` y SQLite siguen sin cambios en este bloque. No publicar ZIP ni aplicar el nuevo mantenimiento.


## Master CoreELEC: comprobación integrada G3-F — PASS

El operador ejecutó `pvr_group_audit_real.py` en el master `192.168.1.102` con M3U local y API Tvheadend de solo lectura. Salida reportada:

```text
=== G3-F INTEGRADO / SOLO LECTURA ===
RESULT=DIAGNOSTIC_ONLY
REASON=NAME_AND_NUMBER_NOT_TECHNICAL_IDENTITY
M3U_CHANNELS=720
TVH_CHANNELS=720
EXACT_NAME_PAIRS=696
NAME_NUMBER_PAIRS=24
RESOLVED_PAIRS=720
UNRESOLVED=0
GROUP_MISMATCHES=0
READ_ONLY=YES
APPLY_AUTHORIZED=NO
```

**Gate de asociación canal-grupo de la instantánea: PASS (720/720; 0 discrepancias).** El estado técnico del comprobador es deliberadamente `DIAGNOSTIC_ONLY`, porque la correspondencia se basa en nombre/número y no en CUID o identidad técnica permanente. No convierte el resultado en autorización de escritura.

Próximos gates: observar orden real de categorías en Kodi; determinar si TVH puede releer la M3U inmediatamente sin reiniciar; confirmar propiedad/uso de las seis etiquetas históricas antes de cualquier borrado. Mantener el reconciliador activo antiguo mientras no exista corte validado; no tocar SQLite ni publicar ZIP.
