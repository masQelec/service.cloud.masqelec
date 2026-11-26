# PVR-02 — Enrutamiento cloud por version de Kodi

Fecha: 2026-11-26
Estado: VALIDADO EN DESARROLLO
Despliegue en MASTER: PENDIENTE
Publicacion de release: NO AUTORIZADA

## 1. Objetivo

Separar la distribucion de recursos cloud de las ramas
de desarrollo del codigo fuente.

Cada version principal de Kodi selecciona automaticamente
su rama numerica en masQelec/cloud.masqelec.

Ejemplos:

- Kodi 21 -> 21
- Kodi 22 -> 22
- Kodi 23 -> 23

El repositorio del addon conserva develop como rama
de trabajo y main como rama estable.

## 2. Arquitectura

Repositorio de codigo:

    masQelec/service.cloud.masqelec

Repositorio de distribucion:

    masQelec/cloud.masqelec

Base RAW para Kodi 21:

    https://raw.githubusercontent.com/masQelec/cloud.masqelec/21

La version se obtiene mediante JSON-RPC interno:

    Application.GetProperties
    properties: ["version"]

No se deduce la version de Kodi a partir de la version
del sistema operativo.

No existe fallback automatico a develop, master o main.

## 3. Inicializacion

constants.py permanece independiente de xbmc.

Antes del arranque de Kodi:

    CLOUD_BRANCH = None
    CLOUD_RAW_BASE = None

service.py inicializa las rutas antes de importar
los consumidores funcionales.

Esto evita que catalog_utils, core_catalog y
update_library almacenen rutas antiguas al importarse.

Una vez inicializada, la ruta no puede cambiar
a otra version durante la misma sesion.

Una respuesta JSON-RPC invalida bloquea la
inicializacion sin seleccionar una rama alternativa.

## 4. Consumidores cloud

Se han auditado:

- catalog_utils.py
- core_catalog.py
- cloud_storage.py
- update_library.py
- update_pvr.py
- rclone_token_sync.py
- rclone_two_mount_client_worker.py
- rclone_two_mount_master_runtime.py
- rclone_two_mount_master_sync.py
- rclone_two_mount_publish_guard.py
- rclone_two_mount_v2_publication.py

La publicacion MQC2 requiere una rama explicita.

El transporte GitHub fija la rama durante la operacion.
Las lecturas, publicaciones y verificaciones posteriores
deben utilizar el mismo destino.

Se mantienen los controles de autorizacion, rol,
salud OAuth, CAS, SHA y confirmacion remota.

Solo la rama 21 esta actualmente autorizada para
el transporte rclone de la nueva distribucion.

Resolver una futura rama 22 o 23 no implica
autorizar automaticamente su operativa rclone.

## 5. Repositorio cloud

Rama 21 creada desde develop.

Commit verificado durante PVR-02F y PVR-02G6C:

    98878154ff7bf51e32dd6aa66e498b2eef262e76

Rama master estable:

    da100abdafcdb1659f99ac7a9b25336bf6e86e47

Recursos comprobados:

- catalog/catalog.zip
- catalog/catalog.version
- pvr/playlist.m3u
- pvr/tv_grab_file
- rclone/rclone.conf.crypt
- rclone/rclone-v2.conf.crypt
- system.d/
- userdata/
- rollouts/

Verificacion RAW del tv_grab_file mediante SHA256:

    32051474eddcff9184b834dd6a1df6e9a7698071ab5c52af98d5ff09cd4c46a7

Las ramas master y develop se conservan para los
dispositivos con versiones anteriores del addon.

Antes del cambio real del MASTER se debe verificar
de nuevo la sincronizacion de recursos y tokens.

## 6. Recuperacion temprana rclone

El ejecutor systemd anterior al arranque de Kodi
puede importar las constantes sin inicializar cloud.

Se ha ejecutado el punto de entrada real del runner
con estados locales simulados:

    EARLY_BOOT_MASTER=PASS
    EARLY_BOOT_CLIENT=PASS
    EARLY_BOOT_ROUTE_UNCHANGED=PASS

Los dos roles devolvieron NO_PENDING.

Regresion especifica early boot:

    Ran 34 tests
    OK

No se han utilizado montajes, cuentas OAuth ni
servicios systemd reales en esta validacion.

## 7. Incidencias resueltas

La activacion del selector detecto pruebas antiguas
que dependian de develop como valor implicito.

Se corrigieron los entornos simulados para proporcionar
explicitamente la rama correspondiente.

Dos pruebas de permisos fallaban bajo umask 077.

Se corrigieron mediante chmod explicito en las
fixtures, sin relajar los controles funcionales.

Las herramientas historicas de laboratorio conservan
sus referencias originales para reproducibilidad.

No se deben reutilizar esas herramientas sobre una
release numerica sin revisar sus restricciones.

## 8. Resultados de regresion

| Fase | Pruebas |
|------|---------|
| Baseline PVR-01 | 1319 |
| PVR-02B | 1328 |
| PVR-02CD | 1337 |
| PVR-02E1 | 1343 |
| PVR-02E2 | 1350 |
| PVR-02G5B | 1357 |

Regresion final:

    STANDALONE_REGRESSION=PASS
    KODI21_REGRESSION=PASS

1357 pruebas en cada entorno.
2714 ejecuciones sin fallos ni errores.

38 pruebas nuevas respecto al baseline.

Los dos entornos son pruebas de desarrollo.
Kodi 21 se simula mediante JSON-RPC.

## 9. Gates

    PVR_02B_FINAL=PASS
    PVR_02CD_FINAL=PASS
    PVR_02E1_FINAL=PASS
    PVR_02E2_FINAL=PASS
    PVR_02F_FINAL=PASS
    PVR_02G1_ACTIVATION=PASS
    PVR_02G4_FINAL=PASS
    PVR_02G5B_FINAL=PASS
    PVR_02G6B_FINAL=PASS
    PVR_02G6_FINAL=PASS

## 10. Limitaciones y validaciones pendientes

- Arranque real del addon sobre CoreELEC.
- Comportamiento ante fallos transitorios de JSON-RPC.
- Recuperacion real tras interrupcion electrica.
- Validacion de publicacion MQC2 real desde MASTER.
- Confirmacion de recursos cloud actuales antes del cambio.
- Restauracion aislada del respaldo PVR-01D.
- Compatibilidad efectiva con futuras versiones de Kodi.

No se ha instalado el addon modificado en MASTER.

No se ha publicado una nueva version para CLIENTES.

## 11. Continuidad del desarrollo

Siguiente fase: PVR-03.

Implementar actualizador automatico de service.tvheadend43:

- Deteccion de plataforma NG o NE.
- Deteccion de arquitectura y compatibilidad CoreELEC.
- Manifiesto de versiones en cloud/<Kodi>/pvr/tvheadend/.
- Comparacion con la version instalada.
- Descarga y validacion SHA256 del ZIP.
- Instalacion controlada.
- Conservacion de configuracion y datos Tvheadend.
- Verificacion posterior y rollback.
- Aplazamiento de operaciones disruptivas si hay
  reproducciones, grabaciones o suscripciones activas.
- Integracion posterior en el mantenimiento PVR.

No crear repositorios Kodi adicionales para NG y NE.

El usuario conserva el control de la publicacion final.

## 12. Metodo de trabajo

1. Auditoria del codigo existente.
2. Preflight de solo lectura.
3. Cambios acotados y verificables.
4. Pruebas unitarias.
5. Regresion completa.
6. Validacion aislada en laboratorio Ubuntu.
7. Validacion controlada en MASTER.
8. Documentacion y commit.
9. Publicacion solo por el responsable del proyecto.

No modificar /system.
No publicar releases durante el desarrollo.
No alterar directamente las bases de datos PVR de Kodi
en la futura arquitectura nativa.
