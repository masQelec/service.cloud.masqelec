# Puerta de compatibilidad STRM / dos cuentas OneDrive

**Estado:** laboratorio local de solo lectura. No autoriza cutover.

## Contrato innegociable

- Los ficheros `.strm` existentes no se editan, regeneran ni trasladan.
- Para cada cuenta, el punto de montaje nuevo debe ser **idéntico, carácter por carácter**, al anterior.
- Las dos cuentas no pueden compartir ni intercambiar el mismo punto de montaje.
- La biblioteca Kodi no se actualiza ni se escanea como parte de esta verificación.
- El script jamás accede al contenido multimedia, OAuth, OneDrive, rclone, FUSE ni systemd.

## Ejecución

Crear **fuera del repositorio**, en un directorio privado del equipo, un JSON con esta estructura (sustituir marcadores por rutas reales; no subir el JSON a GitHub):

```json
{
  "accounts": [
    {
      "id": "account-1",
      "old_mount": "/RUTA/REAL/CUENTA1",
      "new_mount": "/RUTA/REAL/CUENTA1",
      "sample_strm": ["/RUTA/LOCAL/MUESTRA1.strm"]
    },
    {
      "id": "account-2",
      "old_mount": "/RUTA/REAL/CUENTA2",
      "new_mount": "/RUTA/REAL/CUENTA2",
      "sample_strm": ["/RUTA/LOCAL/MUESTRA2.strm"]
    }
  ]
}
```

El valor `new_mount` se obtiene de la **configuración candidata real del nuevo sistema**, no copiándolo a ciegas de `old_mount`. El valor `old_mount` se obtiene de la configuración actualmente instalada. Ambos deben ser rutas absolutas y normalizadas.

```bash
chmod 600 /ruta/privada/mount-path-manifest.json
python3 service.cloud.masqelec/tools/strm_mount_path_gate.py \
  --manifest /ruta/privada/mount-path-manifest.json
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_strm_mount_path_gate.py' -v
```

Salida de aceptación: `MOUNT_PATH_EQUIVALENCE=PASS`, muestras válidas para las cuentas 1 y 2, `CUTOVER_AUTHORIZED=NO`.

Salida de rechazo: `MOUNT_PATH_EQUIVALENCE=FAIL`, `CUTOVER_AUTHORIZED=NO`, código de salida 2. No se imprimen las rutas ni el contenido STRM.

## Alcance y limitaciones

La puerta valida **solo** rutas locales absolutas dentro de muestras `.strm` de una línea, incluidas las variantes `file://`. Si Kodi utiliza `special://`, `smb://`, URL de complemento u otro formato, el verificador **falla cerrado**; no permite inferir compatibilidad. No comprueba todos los `.strm` ni verifica la reproducción real o que el nuevo montaje exponga la misma estructura interna. El resultado `PASS` es condición necesaria, no suficiente, para migrar.

Antes de un cutover futuro se deberán auditar además: plan de retirada de systemd, ausencia de mounts huérfanos, permisos, estructura de directorios, prueba de reproducción real, manejo de fallo/interrupción y recuperación. Nunca activar simultáneamente dos montajes sobre el mismo destino.

## Estado de seguridad

```text
LAB_MODE=LOCAL_STRM_PATH_EQUIVALENCE_READ_ONLY
REAL_OAUTH_PROBE_ALLOWED=NO
CUTOVER_AUTHORIZED=NO
STRM_FILES_CHANGED=NO
FUSE_OR_SYSTEMD_CHANGED=NO
```
