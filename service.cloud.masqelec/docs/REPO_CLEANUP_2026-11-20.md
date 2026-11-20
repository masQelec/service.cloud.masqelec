# Limpieza controlada del repositorio — 20/11/2026

## Contexto

El addon `service.cloud.masqelec` v2.3.2 superó 1025/1025 tests antes de
la limpieza y pasó validación física en MASTER y CLIENT piloto: 2 FUSE,
4 bind, reproducción, limpieza de OneDrive del `rclone.conf` general.
La función de recuperación ante revocación OAuth real sigue pendiente.

La limpieza afecta **solo al código versionado en `develop`**.
No se desinstalan servicios, montajes ni credenciales de equipos; tampoco
se modifica `cloud.masqelec` ni el repositorio de ZIP que publica el operador.

## Eliminado por obsolescencia operativa

Los scripts siguientes tenían como propósito único la investigación anterior
al despliegue; algunos descargaban módulos fijados a SHAs de noviembre
de 2026 y ya no representaban el addon actual:

- `tools/rclone_mount_isolation_lab.py`: laboratorio inicial de cuatro FUSE.
- `tools/rclone_two_mount_plan_lab.py`: generador exploratorio estático.
- `tools/rclone_oauth_lab_setup.sh`: bootstrap de código fijado a commit antiguo.
- `tools/rclone_oauth_pilot.py`: simulación de OAuth legacy.
- `tools/rclone_two_mount_fuse_bind_local_lab.py`: piloto local previo al corte.
- `tests/test_rclone_oauth_pilot.py`: tests de la herramienta OAuth retirada.
- `tests/test_rclone_two_mount_fuse_bind_local_lab.py`: tests exclusivos del piloto local.
- `tests/test_rclone_two_mount_systemd_local_lab.py`: tests exclusivos
  del script systemd exploratorio (los tests de seguridad del ciclo y
  rollback systemd permanecen).

**Importante:** `tools/rclone_two_mount_systemd_local_lab.py` se conserva.
La primera retirada reveló dependencias de dos tests aún útiles,
`test_rclone_two_mount_systemd_account_cycle.py` y
`test_rclone_two_mount_systemd_fake_rollback.py`; el fichero se restauró
antes de cerrar la limpieza. No borrar sin trasladar antes sus helpers y
comprobar CI. `tools/rclone_two_mount_reboot_journal_lab.py` también se
conserva porque lo importa el runner de recuperación temprana bajo un gate
de laboratorio explícito.

## Conservado deliberadamente

- Toda la lógica de producción en `lib/`, `service.py`, `addon.xml`
  y los artefactos del addon.
- Herramientas de diagnóstico operativas, lectura remota, comprobación de
  OAuth, recovery anterior a Kodi y sus tests.
- Tests de integración, transacciones OAuth por cuenta, crash recovery,
  FUSE/bind, Kodi path contract, rotación y publicación MQC2.
- Documentos de auditoría histórica: son evidencia, no runbooks de despliegue.
  Las órdenes antiguas que descargan scripts de commits históricos pueden
  seguir siendo reproducibles por SHA, pero no deben ejecutarse como parte
  del procedimiento actual.

## Política de limpieza

1. Buscar importaciones y referencias antes de borrar un fichero.
2. Mantener los tests que protegen una ruta de producción aunque mencionen
   un laboratorio antiguo.
3. Nunca escribir ni comparar bytes OAuth en salida de CI.
4. Exigir `python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py' -q`
   y GitHub Actions `develop unit tests (no deployment)` en verde tras cambios.
5. Si falla una importación por un helper eliminado, restaurar el helper
   o migrar el test con garantía equivalente; no eliminar ciegamente el test.
6. Revisión posterior opcional: reducir documentación histórica solo tras
   fijar un índice, sin borrar handoffs de auditoría que permiten reconstruir
   incidentes CoreELEC/OneDrive.

## Estado de verificación de la limpieza

La primera CI con el script systemd local retirado falló **solo por dos
importaciones** desde pruebas que lo necesitan. Se restauró el fichero.
La última suite exitosa previa a la limpieza fue 1025/1025. La nueva
suite requiere ejecución/confirmación del workflow y no debe darse por
aprobada de antemano.
