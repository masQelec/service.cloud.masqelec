# PVR-03 — Actualizador transaccional de Tvheadend

Fecha de validacion: 2026-11-26
Rama de desarrollo: develop
Estado: NG MASTER validado funcionalmente.
Distribucion a produccion: NO AUTORIZADA.

## 1. Objetivo

Integrar la actualizacion de service.tvheadend43 dentro del
mantenimiento PVR de service.cloud.masqelec.

El mismo mecanismo debe funcionar en MASTER y CLIENTES.
Cada dispositivo utiliza su propio servidor Tvheadend local.

No crear repositorios Kodi independientes por arquitectura.
La seleccion del paquete corresponde al addon de mantenimiento.

## 2. Distribucion

Repositorio de codigo:
masQelec/service.cloud.masqelec

Repositorio de configuracion y distribucion:
masQelec/cloud.masqelec

Rama de datos determinada por la version mayor de Kodi.
Para Kodi 21 se utiliza exclusivamente la rama 21.

Base RAW:
https://raw.githubusercontent.com/masQelec/cloud.masqelec/21

No utilizar fallback automatico a otras ramas.

Seleccion estricta por:
- Arquitectura de CoreELEC.
- Version de CoreELEC.
- Identificador exacto del build.
- Version del addon.
- Tamano del ZIP.
- SHA256 del ZIP.
- Compatibilidad ELF.

No instalar paquetes en plataformas no validadas.
No realizar downgrade automatico.

## 3. Plataformas

NG:
Amlogic-ng.arm
ELF32 ARM, machine 40.

NE:
Amlogic-ne.aarch64
ELF64 AArch64, machine 183.

MASTER real:
CoreELEC 21.2.5
Build 21.2.5-Omega_devel_20250919152246
Kodi 21.
Arquitectura Amlogic-ng.arm.

La arquitectura del kernel no sustituye la deteccion
de la arquitectura real del addon.

## 4. Paquetes compilados

NG 21.2.8:

Tamano: 32654890 bytes.

SHA256 ZIP:
282e8169c51c8bb30a1ca0e1b47ec4dde5ecd91cc122092d6617bb6efbde45e3

SHA256 binario:
6c87ff5c3de2023373b9e36571f5de9848c074cddaafb995bfbd00089712cc80

NE 21.2.8:

Tamano: 34641758 bytes.

SHA256 ZIP:
ecabb995f8ce3f6f33da940045367f120aadcd97df717a73655dd46ed1d0170d

SHA256 binario:
cf6db2cd3709384b861bb8b6f5f39f2c21881a7817be4ce4a4ccf1ba8a340d38

NE validado en laboratorio simulado.
Pendiente de validacion en dispositivo real.

El manifiesto candidato no constituye autorizacion
para publicar ni desplegar los paquetes.

## 5. Arquitectura de modulos

tvheadend_platform:
Deteccion estricta de plataforma y build.

tvheadend_manifest:
Validacion del manifiesto de distribucion.

tvheadend_version:
Comparacion de versiones y seleccion de actualizaciones.

tvheadend_package:
Descarga y validacion de paquetes.

tvheadend_activity:
Deteccion de reproducciones Kodi, actividad Tvheadend,
suscripciones, grabaciones y ventanas de seguridad DVR.

tvheadend_kodi:
Control nativo mediante JSON-RPC y UpdateLocalAddons.

tvheadend_health:
Estado systemd, procesos, identidad del ejecutable,
SHA256, HTTP autenticado y disponibilidad TCP HTSP.

tvheadend_backup:
Respaldo verificado de la configuracion.

tvheadend_restore:
Restauracion controlada de la configuracion.

tvheadend_staging:
Preparacion del candidato y conservacion del grabber.

tvheadend_transaction:
Intercambio atomico de directorios y diario persistente.

tvheadend_updater:
Maquina de estados de instalacion y recuperacion.

tvheadend_lifecycle:
Bloqueo persistente, parada nativa, normalizacion
segura de systemd, archivado y reparacion del servicio.

tvheadend_boot:
Recuperacion de archivos antes del arranque de Kodi.

tvheadend_boot_install:
Instalacion persistente del protector systemd.

tvheadend_update_policy:
Regla individual de actualizacion del addon en Kodi.

tvheadend_boot_policy:
Aplicacion offline de la regla y marcador del boot.

tvheadend_release_control:
Bloqueo por identidad exacta de paquete fallido
y retencion de transacciones archivadas.

tvheadend_update_service:
Coordinacion de actualizacion y recuperacion.

tvheadend_runtime:
Adaptador comun para MASTER y CLIENTES.

## 6. Transaccion

Directorio activo:
 /storage/.kodi/addons/service.tvheadend43

Configuracion:
 /storage/.kodi/userdata/addon_data/service.tvheadend43

Raiz de transaccion:
 /storage/.kodi/userdata/addon_data/service.cloud.masqelec/tvheadend-update

Estados:

PREPARED
DISABLING
BACKED_UP
SWAPPED
STARTING
COMMITTED
ROLLING_BACK
ROLLBACK_STARTING
ROLLED_BACK
CANCELLED

El intercambio de directorios utiliza renameat2
con RENAME_EXCHANGE en el mismo sistema de archivos.

No sustituir archivos del addon mientras existan
procesos de Tvheadend.

La configuracion debe respaldarse y verificarse
antes del intercambio de versiones.

La recuperacion de una transaccion pendiente tiene
prioridad sobre cualquier nueva descarga.

No iniciar otra instalacion en el mismo ciclo
que recupera una transaccion anterior.

## 7. Proteccion de arranque

Servicio persistente:

/storage/.config/system.d/masqelec-tvh-recovery.service

Drop-ins:

kodi.service.d/60-masqelec-tvh-recovery.conf

service.tvheadend43.service.d/60-masqelec-tvh-recovery.conf

service.tvheadend43.service.d/65-masqelec-tvh-stop.conf

El protector ejecuta la recuperacion antes de Kodi
y Tvheadend.

Kodi utiliza Wants y After.

Tvheadend utiliza Requires y After.

No modificar /system.

No modificar directamente las unidades originales.

## 8. Politica individual de actualizacion

Base de datos:
 /storage/.kodi/userdata/Database/Addons33.db

Regla:
 service.tvheadend43, updateRule=1

Solo se incorpora durante el arranque temprano,
con Kodi y Tvheadend detenidos.

Se verifica esquema, integridad, propietario y permisos.

Se crea respaldo SQLite antes de insertar la regla.

No modificar otras reglas de actualizacion.

Marcador:
 /run/masqelec-tvh-policy-ready

El marcador acredita el boot actual y la identidad
del archivo SQLite.

La regla impide la actualizacion automatica ordinaria
del addon por Kodi.

No constituye un bloqueo absoluto frente a operaciones
manuales u otros instaladores externos.

## 9. Incidencias reales detectadas

### PVR-03I7

Directorios y archivos con permisos 0775 y 0664.

Se corrigieron exclusivamente permisos de archivos
identicos y directorios conocidos.

No se sobrescribieron archivos incompatibles.

### PVR-03I8B

La transferencia TAR con propietario de Ubuntu
provoco un rechazo del entorno privado.

Solucion:
Transferir con owner=0, group=0 y numeric-owner.
Verificar propietario, permisos e integridad.

### Inventario PVR

El nombre real de la columna del cliente Kodi es
iClientId, no idClient.

Las consultas de diagnostico utilizan SQLite en
modo de solo lectura.

### PVR-03I8C

La unidad original establecia TimeoutStopSec=2.

Tvheadend guardaba la EPG durante la parada,
pero systemd enviaba SIGKILL tras dos segundos.

La unidad era eliminada por el wrapper de CoreELEC.

Estado observado:
 LoadState=not-found
 ActiveState=failed
 SubState=failed
 MainPID=0
 ControlPID=0

El actualizador rechazaba correctamente una parada
no confirmada, pero no podia recuperar automaticamente.

El coordinador exigia una unidad TVH cargada incluso
cuando esa unidad habia sido eliminada durante la
deshabilitacion del addon.

### Recuperacion real

Se normalizo systemd mediante reset-failed,
previa comprobacion de ausencia de procesos y trabajos.

Se ejecuto TvheadendUpdater.recover() directamente.

Version original 21.2.7 recuperada.
Configuracion e identidad PVR conservadas.
Kodi no reiniciado.

El candidato nunca llego a instalarse.
No se penalizo el paquete 21.2.8.

## 10. Correcciones PVR-03I9

TimeoutStopSec=60s mediante drop-in persistente.

Parada nativa antes de deshabilitar el addon en Kodi.

Comprobacion del resultado de systemd mientras
la unidad sigue cargada.

No aceptar SIGKILL como parada limpia.

Normalizacion de estados fallidos exclusivamente
en recuperacion y bajo bloqueo.

Separar los requisitos de una nueva instalacion
de los requisitos de recuperacion.

No penalizar un candidato que no alcanzo la fase
en la que podria modificar la configuracion.

Conservar el bloqueo de nuevas instalaciones
cuando exista una transaccion pendiente.

## 11. Validaciones reales NG

### PVR-03I7C

Reinicio real y aplicacion offline de la politica:
PASS.

### PVR-03I9C

Actualizacion real:
21.2.7 -> 21.2.8.

Parada limpia, respaldo, intercambio de directorios,
arranque real, salud y archivado:
PASS.

Sin reinicio de Kodi.

Intervalo entre parada completa y nuevo arranque:
46 segundos.

### PVR-03I9D

Persistencia tras reinicio real:
PASS.

Binario, grabber, politica, timeout, grupos,
identidades y asociaciones conservados.

### PVR-03I9E

Rollback automatico real:
PASS.

Candidato de laboratorio 21.2.9 construido utilizando
el mismo ejecutable de 21.2.8.

SHA256 del ZIP exclusivo de laboratorio:
13a2bc1e340880b94281e2125d9028d25f0167149f4eac92c358232fde506955

El candidato arranco realmente.

Se indujeron 12 fallos en el verificador de salud
despues de comprobar HTTP, HTSP TCP y ejecutable.

Restauracion real de configuracion: 1 llamada exitosa.

Resultado: ROLLED_BACK.

Version final: 21.2.8.

Bloqueo del ZIP de laboratorio: PASS.
Archivado de transaccion: PASS.
Transaccion pendiente: NO.
Reinicio Kodi: NO.
Intervencion manual durante rollback: NO.

## 12. Inventario PVR real

Canales: 714.
Grupos: 54.
Asociaciones: 1428.

Duplicados y asociaciones huerfanas:
0 en la auditoria de persistencia.

SHA256 identidad de canales:

9496740dac9793c0a7dbf51e003bf5c3290df5bfc1080f564996cbac763cf7c0

SHA256 identidad y orden de grupos:

186db7f52da308bb9b97435de748683ff090a7d4a319e5f4b44fc89abd54562a

SHA256 identidad y orden de asociaciones:

1d66c2e8f44b24e5755bf7247660fe6edc75b43d880d81b4591cdcb8e7389410

SHA256 grabber personalizado:

32051474eddcff9184b834dd6a1df6e9a7698071ab5c52af98d5ff09cd4c46a7

Las tres huellas PVR permanecieron identicas
despues del reinicio y del rollback real.

No se realizaron escrituras SQL sobre TV46.db
por parte del actualizador o las pruebas.

## 13. Regresion

Pruebas anteriores: 1622.

Nuevas pruebas PVR-03I9A: 14.

Total validado: 1636 pruebas.
Fallos: 0.

Existen ResourceWarning de pruebas HTTP.
Pendiente de revisar el cierre de esos recursos.

## 14. Restricciones y limitaciones

El rollback real utilizo dos versiones declaradas
distintas del addon con un ejecutable identico.

Por tanto, verifica la restauracion de directorios
y configuracion, pero no la recuperacion real
entre dos ejecutables diferentes.

La comprobacion HTSP es TCP.
No equivale a un handshake HTSP completo
ni a una prueba de reproduccion de television.

La restauracion de configuracion se verifico
mediante la funcion real de restauracion.
No se inyecto corrupcion deliberada de configuracion.

Pendiente:
- Corte electrico real durante una transaccion.
- Recuperacion automatica integrada ante parada
  fallida real, sin intervencion manual.
- Recuperacion ante un nuevo fallo durante rollback.
- Compatibilidad NE en dispositivo real.
- Descarga HTTPS del paquete de distribucion.
- Prueba funcional manual de reproduccion y guia.
- Integracion definitiva con los workers PVR.

No autorizar distribucion general hasta completar
los requisitos operativos correspondientes.

## 15. Modo de trabajo

Desarrollo en Ubuntu.
Pruebas aisladas y regresion completa.
Validacion posterior en MASTER real.
Bloqueos explicitos ante estados desconocidos.
Respaldos antes de operaciones destructivas.
No borrar diarios para resolver errores.
No repetir instalaciones sin inspeccionar el estado.
No publicar paquetes de laboratorio.
No incluir credenciales, configuraciones privadas,
bases de datos o respaldos en Git.

Los ensayos MASTER se ejecutan por SSH y RunScript.

Los scripts tools/tvheadend_master_*_lab.py
son exclusivamente herramientas de validacion.

El usuario gestiona la publicacion de produccion.

## 16. Continuidad: PVR-04/05/06

Auditar y simplificar lib/update_pvr.py.

Eliminar la reconciliacion manual de canales y
grupos que ya resuelve Tvheadend de forma nativa.

Eliminar modificaciones directas de las bases
de datos PVR de Kodi.

Eliminar actualizaciones forzadas de playlist,
reinicios innecesarios y reconstrucciones artificiales.

Mantener la descarga de playlist desde GitHub,
independiente de los montajes rclone.

Validar CUID, integridad y orden de la lista.

Mantener las credenciales y su provision separada.

Gestionar configuracion mediante API nativa TVH.

Deshabilitar la modificacion de nombres de canales
por parte de la guia EPG.

Validar y habilitar scrape_extra en el grabber
XMLTV correspondiente.

Conservar el grabber personalizado.

Verificar la gestion nativa de canales y grupos.

## 17. Continuidad: PVR-07/08

Integrar un worker de arranque y otro periodico.

Ambos deben utilizar la misma rutina de mantenimiento.

Utilizar exclusion mutua entre ejecuciones.

No depender de rclone para arrancar el mantenimiento PVR.

Diferenciar exito, aplazamiento y fallo.

Recuperar transacciones pendientes antes de exigir
la proteccion completa de una nueva instalacion.

No llamar incondicionalmente a la instalacion del
protector cuando exista una transaccion pendiente.

No aplicar una comprobacion global de inactividad
a operaciones no disruptivas.

Reservar las restricciones de actividad para
actualizaciones y cambios que interrumpan servicios.

MASTER y CLIENTES deben compartir el actualizador.

Validar el ciclo completo antes de integrar en main.

## 18. Independencia de umask

Durante la regresion previa al commit se detecto
un error en test_existing_conflict_preserved.

El directorio del entorno de pruebas dependia
del umask heredado del proceso.

Se corrigio la creacion del directorio mediante
permisos explicitos 0700.

Regresion del instalador con umask:
- 002: PASS.
- 022: PASS.
- 077: PASS.

Regresion completa con umask 002: PASS.

No se han relajado las comprobaciones de seguridad
del instalador ni modificado el codigo de produccion
para resolver esta incidencia.
