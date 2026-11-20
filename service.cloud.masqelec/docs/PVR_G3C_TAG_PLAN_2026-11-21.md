# G3-C — Planificación de categorías Tvheadend sin escrituras

Fecha: 2026-11-21. Rama: develop. Módulo: `lib/pvr_tag_plan.py`. Tests: `tests/test_pvr_tag_plan.py`.

## Evidencia del master (confirmación del operador)

- `iptv_auto_network` UUID `cce41e6f2d9b5d829d3af38159eea0a5`, nombre `IPTV LOCAL`, habilitada.
- `num_mux=num_svc=num_chn=720`; `refetch_period=1` durante pruebas (el operador confirma 60 como valor habitual).
- `channeltag/grid`: 32 categorías. `channel/grid`: 720/720, ninguna sin categorías, 26 categorías utilizadas.
- `channeltag/create` creó una categoría temporal y `idnode/delete` la eliminó; se verificó recuperación de los 32 UUID originales.
- Los 26 nombres de grupos de la M3U coinciden con categorías de TVH, pero el campo `index` de numerosas categorías es cero. No se ha demostrado que Kodi muestre el mismo orden.
- Seis etiquetas vacías: `3e6be21d508c4effb8de6195294739b9`, `4c868c19255541598f992aa58b18ddf6`, `1152413dbf7b4d70b551411eb555c224`, `50b0f8d1ebf340b981bd3bc2d589b8b7`, `7644c62eaec0428b91fa0c3f376a7e69`, `e4203837a12f47ff9823b3a8ac41d2ef`.
- Estas seis etiquetas **no se deben borrar automáticamente** sin corroborar propiedad y alcance; el experimento G3-A demostró capacidad de API, no autorización de borrar objetos preexistentes.

## Diseño implementado en develop

`m3u_groups(m3u_text)` extrae nombres de grupos en orden de primera aparición, sin usar `set` para determinar orden.

`plan(m3u_text, tvh_tags_snapshot, tvh_channels_snapshot, owned_tag_uuids)` devuelve candidatos de creación, cambio de índice y borrado de categorías vacías **previamente registradas como propiedad del addon**. Nunca invoca endpoints ni escribe ficheros. `apply_authorized=False` es incondicional.

Bloqueos: M3U vacía, grupos omitidos, inventarios paginados/incompletos, recuentos M3U/TVH distintos, nombres/UUID ambiguos, enlaces a categorías desconocidas, canales sin categoría, registro de propiedad obsoleto.

## Limitaciones deliberadas y gates pendientes

1. Igualdad 720/720 y nombres iguales **NO demuestra** que sean los mismos canales. Antes de cualquier aplicación se requiere verificación de inventario por identidad técnica (CUID cuando sea propagado y probado, o mapeo de servicio/HTSP verificado), más evidencia de que TVH terminó el ciclo de lectura.
2. No está probado todavía `idnode/save` para `index`, ni que `index=1..26` produzca el orden deseado en Kodi. Primero ensayo con una etiqueta temporal; no modificar los 26 grupos reales para probar.
3. No está preparado el mecanismo de propiedad: para el primer uso, las etiquetas existentes deben ser adoptadas de forma controlada. No inventar propiedad a partir de nombre o ausencia de canales.
4. La nueva implementación todavía NO está conectada a `update_playlist()` y el reconciliador histórico sigue en el código existente. **No publicar ZIP ni ejecutar corte hasta separar y probar ese flujo**.
5. La futura aplicación debe hacer copia/rollback, considerar DVR/reproducción, persistir estado tras confirmación y verificar relaciones finales. Nunca borrar directamente `tag/` en caliente.
6. Los tests añadidos al repositorio no equivalen a CI pasada. Ejecutar `python3 -m unittest discover -s service.cloud.masqelec/tests -p test_pvr_tag_plan.py -v` desde la raíz del repositorio y revisar CI.

Siguiente gate: G3-D, experimento `idnode/save` sobre un tag temporal de laboratorio, restauración comprobada; después añadir cliente API de lectura y verificación completa de asociaciones, y solo más adelante el aplicador protegido.
