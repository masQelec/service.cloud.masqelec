# MASTER readiness previo al ensayo operativo — 19/11/2026

Se añade `tools/master_cutover_readiness.py`, autónomo, sin imports Kodi. Es **solo lectura**. Comprueba condiciones adicionales no cubiertas por el preflight anterior: permisos de directorios, privacidad de configuración sin leer sus contenidos, ausencia de transacciones/artefactos v2 previos y espacio libre de reserva (mínimo 16 MiB). **No es ejecutor de cutover**.

## Procedimiento

**Ubuntu**: pruebas unitarias antes de copiar nada al MASTER:

```sh
cd ~/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_master_cutover_readiness.py' -v
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_*.py'
```

**MASTER**, por SSH: transferir solo `tools/master_cutover_readiness.py` a `/tmp`; ejecutar `python3 /tmp/master_cutover_readiness.py --read-only`. El operador no necesita instalar el addon nuevo ni iniciar ningún servicio.

Se esperan once campos PASS y `MASTER_READINESS=PASS_READ_ONLY`. Una condición BLOCKED no debe corregirse borrando artefactos de manera automática: primero inspeccionar estado y journal. El diagnóstico no valida reproducción inactiva ni tokens OAuth y no autoriza parada de servicios.

## Requisitos posteriores (aún pendientes)

1. Obtener prueba de Kodi inactivo mediante JSON-RPC integrado, en el momento del corte.
2. Validar protocolo probado de recuperación y corte de alimentación en MASTER, con respaldos durables.
3. Auditar los posibles escritores OAuth del MASTER y la coexistencia de tokens con CLIENTES; no asumir independencia OAuth por independencia de montajes.
4. Autorizar expresamente una ventana de ensayo real solo después de superar esos gates; mantener los destinos STRM sin cambios.
5. Reproducción, reinicio y limpieza legacy solo después de ACTIVE verificado.

```text
CUTOVER_AUTHORIZED=NO
REAL_OAUTH_PROBE_ALLOWED=NO
LEGACY_CLEANUP_AUTHORIZED=NO
```
