# G3-F/B1 — Bloque consolidado de auditoría IPTV/PVR

Fecha: 2026-11-21. Estado: `develop`, exclusivamente diagnóstico.

## Evidencia real ya obtenida

- G3-A: API de Tvheadend crea y elimina un tag temporal; inventario restaurado.
- G3-B: M3U 26 grupos; TVH 32 tags, 26 utilizados, 6 vacíos.
- G3-C: planificador puro `pvr_tag_plan.py`: 13/13 tests OK comunicados por el operador.
- G3-D: `idnode/save` del índice de tag temporal a 99, lectura posterior y borrado; inventario restaurado.
- G3-E: nombres exactos únicos, 696/696 asociaciones de grupo correctas; 24 ambiguas por nombre.
- G3-F: en master, las 24 adicionales se desambiguaron por (nombre,número), 24/24 grupos correctos; suman **720/720 en la instantánea actual**. Esto **no** comprueba identidad CUID ni orden de Kodi.

## Cambios de código agrupados

- `lib/pvr_group_audit.py`: la función `audit()` original sigue disponible. Nueva `audit_with_numbers()` resuelve nombres repetidos únicamente si la pareja nombre/número es única en M3U y TVH. Números incompatibles, ausentes, repetidos o cambiados **no se adivinan**; no se usan como identidad persistente. `apply_authorized=False` siempre.
- `tests/test_pvr_group_audit.py`: 10 casos adicionales (fallback completo, discrepancia, colisión, ausencia, cambio, normalización decimal, números contradictorios, credenciales, ausencia de número, paginación), además de 11 tests anteriores.
- `lib/pvr_tag_plan.py` y tests G3-C no cambian; el planificador conserva el orden de primera aparición, pero **no aplica cambios**.

## Gate local consolidado

Desde la raíz del clon:

```bash
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_tag_plan.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_group_audit.py' -v
```

Esperado: 13+21=34 tests; pendientes de confirmación de ejecución sobre el commit de este bloque.

## Pendiente — pruebas reales agrupables sin cambios en producción

1. Ejecutar el nuevo `audit_with_numbers()` con capturas de `channeltag/grid`, `channel/grid` y M3U local, redacción de salidas; esperar `resolved_pairs=720`, `group_mismatch_count=0`, `apply_authorized=False`.
2. Examinar el orden de categorías en el cliente Kodi y compararlo con el orden de primera aparición M3U; **index de tag TVH no implica automáticamente orden Kodi**.
3. Determinar un mecanismo efectivo de refetch inmediato de M3U sin parar TVH (API scan no equivale necesariamente a refetch).
4. Probar retorno 720→865→720 únicamente con permiso del operador, verificación de DVR y snapshot previo.
5. Adoptar con seguridad propiedad de categorías históricas y construir un aplicador API transaccional con verificación y recuperación; las seis vacías no son automáticamente propiedad del addon.
6. Conservar flujo histórico activo hasta piloto completo y corte explícito. No tocar `TVxx.db`, M3U publicada, EPG, master ni ZIP en este bloque.

**No se habilita todavía sincronización automática ni borrados.**
