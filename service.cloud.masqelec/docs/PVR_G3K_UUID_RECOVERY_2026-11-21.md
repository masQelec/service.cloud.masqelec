# G3-K — Recuperación del UUID con categoría temporal (bloque consolidado)

Fecha: 2026-11-21. Rama `develop`. **No ejecutar borrado de categorías históricas ni modificar TVxx.db.**

## Evidencias reales

- G3-F: 720 canales, 720 asociaciones de grupos coherentes por nombre/número; el resultado es diagnóstico, no identidad CUID.
- G3-G/H: Kodi presenta 26 grupos ocupados y después seis grupos vacíos, ordenados alfabéticamente dentro de cada bloque.
- G3-I: `ES - NBA` (`3e6be21d508c4effb8de6195294739b9`) no está en M3U, no tiene canales TVH asignados y sigue presente en Kodi.
- G3-J: copia privada de la configuración original creada y verificada SHA-256, 2006 archivos de configuración recorridos por bloques, cero UUID directos, cero errores, cero omitidos. `REFERENCE_SCAN_EXHAUSTIVE=NO`, `OWNERSHIP_VERIFIED=NO`, `UUID_RESTORE_PROVEN=NO`, `DELETE_AUTHORIZED=NO`.

## Implementación

`tools/pvr_g3k_temp_tag_uuid_recovery.py` ensaya únicamente con un tag temporal de nombre aleatorio `MASQELEC_G3K_*`:

1. Consulta `channeltag/grid` y `channel/grid`; exige baseline de 32 tags, 720 canales, UUID histórico presente.
2. Crea categoría desechable con `channeltag/create`, obtiene su UUID y lo registra internamente sin exponer otros datos.
3. Comprueba que no tiene canales, borra solo ese UUID temporal por `idnode/delete`, verifica su ausencia.
4. Intenta recrear la etiqueta con `conf.uuid` igual al UUID temporal original; comprueba si la API conserva o ignora ese identificador.
5. Elimina el tag temporal resultante, verifica que el conjunto de UUID de tags coincide exactamente con el inventario inicial; si no coincide, **bloquea** y requiere intervención manual.

El experimento **sí realiza creaciones/borrados de objetos TEMPORALES en el master**, como los ensayos G3-A y G3-D ya autorizados, pero jamás toca `ES - NBA` u otros tags preexistentes. En fallo puede requerir limpieza manual; no modifica configuraciones mediante archivos.

Incluso si `UUID_RECREATED_SAME=YES`, **no prueba** restauración completa de campos, grabaciones o relaciones. Siempre `FULL_CONFIGURATION_RESTORE_PROVEN=NO` y `HISTORIC_DELETE_AUTHORIZED=NO`.

## Gate local, Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3k_temp_tag_uuid_recovery.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3j_tag_backup_preflight.py' -v
```

Esperados: seis tests G3-K y once G3-J. La ejecución todavía debe confirmarla el operador; no afirmar PASS sin salida.

## Gate master, tras tests locales

```bash
scp service.cloud.masqelec/tools/pvr_g3k_temp_tag_uuid_recovery.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3k_temp_tag_uuid_recovery.py'
```

Este ensayo crea y destruye únicamente categorías temporales. Ejecutar fuera de cambios manuales concurrentes de categorías TVH. Si la API ignora `conf.uuid`, el programa puede terminar con código 2 pero `INVENTORY_RESTORED=PASS`: **es un resultado negativo válido**, no una emergencia.

## Decisión según resultado

- `UUID_RECREATED_SAME=NO`: no asumir restauración por API. Diseñar procedimiento de recuperación de configuración con TVH parado en laboratorio/snapshot separado y validación de UUID, sin usar ficheros en caliente.
- `UUID_RECREATED_SAME=YES`: verificar adicionalmente restauración exacta de atributos, vínculos/propiedad y grupos Kodi antes de aplicar limpieza histórica.
- Cualquier error/inventario no restaurado: bloquear y revisar antes de otro ensayo.
- Ningún resultado habilita aún borrado histórico `ES - NBA` ni limpieza automática ni ZIP.

## Próximos bloques

Refresco sin reinicio: probar solo después de aislar un mecanismo demostrado de refetch M3U, no confundir `mpegts/network/scan` con relectura automática. Luego piloto 720→865→720 con snapshots, grabaciones protegidas y comparación Kodi PVR. Mantener flujo activo intacto hasta gate integral.
