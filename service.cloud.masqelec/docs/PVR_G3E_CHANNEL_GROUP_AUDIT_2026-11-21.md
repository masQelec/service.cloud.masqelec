# G3-E — Auditoría read-only canal → grupo

Fecha: 2026-11-21. Rama: `develop`.

## Contexto

G3-A: creación/borrado de un tag temporal por API PASS. G3-B: 26/26 grupos de M3U presentes; seis tags históricos vacíos. G3-C: 13/13 tests del planificador PASS informados por el operador. G3-D: `idnode/save` sobre `index=99` de tag temporal PASS; restauración de 32 UUID originales PASS.

## Implementación

`lib/pvr_group_audit.py`: función pura `audit(m3u_text, tags_grid, channels_grid)`. Solo interpreta datos suministrados; no abre URLs, archivos ni bases de datos y no escribe.

- Verifica totales de paginación de ambas cuadrículas.
- Extrae `group-title` y nombre de cada `#EXTINF` sin leer las URLs privadas de reproducción.
- Compara solo nombres exactos únicos tanto en M3U como en TVH.
- Denuncia grupos divergentes en los pares verificables por nombre.
- Declara `INCONCLUSIVE` si hay nombres transformados/duplicados.
- Declara `DEFERRED` si el recuento no ha convergido, y `BLOCKED` ante snapshots incompletos o enlaces de tag desconocidos.
- El reporte es diagnóstico, **no es prueba de CUID ni de identidad de servicios**: `apply_authorized=False` siempre.

Tests en `tests/test_pvr_group_audit.py`, incluyendo grupos correctos/incorrectos, duplicados, renombrados, paginación, referencias inválidas y no filtración de contraseñas.

## Ejecución

Desde raíz Git:

```bash
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_group_audit.py' -v
```

Pendiente: tests reales informados por el operador; no afirmar PASS de G3-E todavía.

## Gates siguientes

1. Recoger snapshot real de `channel/grid` con `name, uuid, tags` y `channeltag/grid` tras lectura automática de la M3U; no copiar URLs privadas.
2. Probar auditoría read-only con inventario real y producir únicamente recuentos; verificar divergencias y explicar pares no identificables.
3. Capturar identidad técnica CUID → TVH UUID/servicio → Kodi, solo si la API realmente ofrece información verificable; en otro caso permanecer en diagnóstico.
4. Verificar orden en Kodi por separado. No cambiar índices de los 26 grupos existentes.
5. No conectar este módulo todavía con `update_playlist`; conservar el control de rollout en `develop`, sin ZIP ni live edits.
