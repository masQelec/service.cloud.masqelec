# PVR master — criterio EPG opcional

Aclaración del operador (20-11-2026): **no es relevante que la guía EPG cubra todos los canales**.

## Gate funcional

- Un canal con CUID válido y correctamente importado en TVH/Kodi es válido aunque no tenga `tvg-id`, XMLTV correspondiente o programas en la guía.
- La ausencia de EPG y la cobertura parcial **no bloquean** G0–G8 ni la migración del master.
- El `tvg-id` tampoco es un identificador estable ni necesariamente único: no utilizarlo para reconciliar altas, bajas o identidad de canales.
- Mantener el grabber y la EPG existentes; no modificar `guide.xml` ni forzar actualizaciones por ausencia de programación.
- Un fallo EPG real, atribuible a los cambios y que degrade una EPG que ya funcionaba, debe documentarse como regresión independiente; no confundirlo con falta de cobertura anterior.
- Los criterios PVR que sí importan son inventario de TVH y Kodi, identidad verificada, números, orden, grupos, bajas de huérfanos, no disrupción de DVR/reproducción y recuperación comprobada.

Esta aclaración complementa los documentos de diseño previos. No modifica el motor de sincronización ni autoriza borrados de SQLite.
