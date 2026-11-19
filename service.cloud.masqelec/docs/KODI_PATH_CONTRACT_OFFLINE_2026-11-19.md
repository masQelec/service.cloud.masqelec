# Gate offline: rutas Kodi intactas al pasar a 2 FUSE + 4 bind

Estado: **solo pruebas de generación en Ubuntu**; sin autorización para activar montajes.

## Invariantes

Las referencias `.strm` locales son inmutables. La arquitectura candidata usa dos raíces FUSE internas
`/storage/.mnt/cloud/{1,2}`, pero mantiene exactamente las rutas antiguas en Kodi:

| Cuenta | Origen bind candidato | Destino Kodi anterior |
| --- | --- | --- |
| 1 | `/storage/.mnt/cloud/1/movies` | `/storage/.mnt/videos/1` |
| 1 | `/storage/.mnt/cloud/1/tvshows` | `/storage/.mnt/tvshows/1` |
| 2 | `/storage/.mnt/cloud/2/movies` | `/storage/.mnt/videos/2` |
| 2 | `/storage/.mnt/cloud/2/tvshows` | `/storage/.mnt/tvshows/2` |

`tests/test_rclone_two_mount_kodi_path_contract.py` valida con fixtures sintéticos:
1. Exactitud del conjunto de destinos legacy y de los bind.
2. Comandos `mount --bind`, `umount` y el control previo de destino vacío/no montado.
3. Montajes rclone raíz aislados de los cuatro destinos Kodi.
4. Inventario de seis unidades y dos configuraciones privadas.
5. Ausencia de archivos `.strm` entre los artefactos generados.

## Ejecución

```sh
cd ~/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_rclone_two_mount_kodi_path_contract.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

El test no lee configuraciones OAuth reales, no usa OneDrive, ni modifica systemd/FUSE.
La presencia de rutas en el plan **no demuestra** equivalencia física de los árboles,
acceso a ficheros ni reproducción Kodi. La validación física posterior requiere una
versión candidata copiada por el operador al MASTER, preflight aislado y rollback comprobado.

```text
CUTOVER_AUTHORIZED=NO
REAL_OAUTH_PROBE_ALLOWED=NO
STRM_FILES_CHANGED=NO
FUSE_OR_SYSTEMD_CHANGED=NO
```
