# G0 — recogida de evidencias Kodi / Tvheadend / pvr.hts (solo lectura)

**Estado:** pendiente de evidencia del dispositivo real. Ninguna operación de producción autorizada.

## Alcance y restricciones

No editar playlist, EPG, ficheros de configuración de Tvheadend, `TVxx.db`, ni reiniciar Kodi/TVH/pvr.hts. No ejecutar el inspector sobre la base activa; requiere una **copia consistente ya creada fuera de `userdata` y `.kodi`**. Una copia hecha con `cp` mientras Kodi escribe puede ser inconsistente: no asumir que es válida. No publicar contraseñas, tokens, URL de streams, contenido de grabaciones ni nombres privados.

## Inventario exigido

1. Versiones exactas de Kodi, `pvr.hts` y Tvheadend; versión de esquema SQLite (`user_version`); identificar qué `TVxx.db` utiliza realmente Kodi. **La numeración del nombre de archivo no acredita actividad.**
2. Tvheadend: export READ-ONLY filtrado de `mpegts/network/grid`, `mpegts/mux/grid`, `mpegts/service/grid`, `channel/grid`, `channel/tag/grid`, `bouquet/grid`, `dvr/entry/grid` y `dvr/config/grid`, según endpoints compatibles con la versión real. Limitar a `IPTV LOCAL`; registrar UUID, números y referencias cruzadas, nunca URL/credenciales. Proteger eventos/grabaciones.
3. Kodi: consultar vía JSON-RPC `Application.GetProperties` (version), `Addons.GetAddonDetails` (pvr.hts), `PVR.GetProperties`, `PVR.GetChannels` y `PVR.GetChannelGroups` (comprobar permisos y propiedades admitidas por la versión concreta). Registrar IDs, números y grupos sin stream URLs. Consultar el detalle de miembros de grupos donde esté disponible.
4. Contrastar snapshots próximos en el tiempo, cuando TVH haya finalizado su ciclo de 60 minutos, con 2–3 huérfanos constatados en Kodi y ausentes de TVH. Si no hay huérfanos reales, usar fixtures; no fabricar bajas en producción.
5. Validar identidad: no suponer `CUID == Kodi channelid`, `CUID == TVH UUID`, ni un nombre como clave única. Sin correlación suficiente, clasificar `BLOCKED_AMBIGUOUS_IDENTITY`.

## Inspector local de snapshot (no conectar con Kodi)

Desde el checkout del repositorio:

```bash
python3 service.cloud.masqelec/tools/pvr_g0_inspect_snapshot.py /ruta/aislada/TV42.db > g0_schema.json
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g0_inspect_snapshot.py' -v
```

`TV42.db` es un **ejemplo**, no la versión del equipo. El inspector opera en `mode=ro` con `query_only`; recoge esquema/columnas/índices/relaciones, recuentos y `PRAGMA quick_check`, nunca valores de streams, canales o credenciales. No obtiene ni crea snapshots automáticamente. Un resultado `READ_ONLY` solo acredita que se pudo leer la copia; **no acredita que sea la DB activa, ni que la copia sea temporalmente consistente**, ni autoriza borrados.

Antes de compartir `g0_schema.json`, revisar por si algún nombre de tabla/columna personalizado contiene datos sensibles. Registrar por separado hashes de los ficheros de evidencia si se necesita trazabilidad, sin publicar ficheros de producción.

## Gate G0 (bloqueante)

- [ ] Versiones Kodi/TVH/pvr.hts acreditadas con evidencia.
- [ ] TVxx.db activa identificada mediante evidencia del dispositivo, no por selección lexicográfica.
- [ ] Snapshots TVH y Kodi obtenidos en el mismo ciclo estable.
- [ ] SQLite offline: esquema, claves foráneas, índices, integridad y relaciones conocidas.
- [ ] 2–3 huérfanos inequívocos, o reproducción sintética documentada si no existen.
- [ ] Validación de protección DVR y reproducción.
- [ ] Revisión de secretos, autorización de alcance y aprobación explícita antes del piloto.

**G0_RESULT=PENDING_REAL_EVIDENCE**. G1/G2 pueden avanzar con fixtures, pero G3/G4 destructivos y piloto siguen bloqueados. La limpieza histórica permanece sin cambios en código.
