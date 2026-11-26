# Cloud masQelec 2.3.2 — Integración PVR y validación final MASTER

Fecha: 2026-11-27
Rama de implementación: develop
Estado MASTER: VALIDADO
Estado CLIENTE: INTEGRACIÓN FINAL APLAZADA
Publicación de paquetes: NO AUTORIZADA

## 1. Objetivo

Mantenimiento automático, fiable e idempotente de KodiELEC,
sin operaciones destructivas innecesarias sobre PVR,
biblioteca, montajes o credenciales.

MASTER y CLIENTES comparten el mismo addon y actualizador.
Cada dispositivo utiliza su propio Tvheadend local.

## 2. Repositorios

Código:
- masQelec/service.cloud.masqelec
- Rama develop

Distribución y configuración:
- masQelec/cloud.masqelec
- Rama determinada por la versión mayor de Kodi.
- Kodi 21 utiliza exclusivamente la rama 21.
- Sin fallback automático a master o develop.

Compilación:
- masQelec/KodiELEC
- Builds Amlogic-ng.arm y Amlogic-ne.aarch64.

EPG:
https://raw.githubusercontent.com/masQelec/epg/main/guide.xml

Base RAW de distribución para Kodi 21:
https://raw.githubusercontent.com/masQelec/cloud.masqelec/21

## 3. Arquitectura definitiva PVR

El mantenimiento de arranque y periódico utiliza un mismo
coordinador: lib/update_pvr.py.

Orden funcional:

1. Recuperación de transacciones Tvheadend pendientes.
2. Verificación o aprovisionamiento de credenciales.
3. Descarga, validación y actualización atómica de playlist.
4. Configuración nativa XMLTV mediante ajustes del addon.
5. Evaluación del actualizador Tvheadend.
6. Configuración nativa de Tvheadend.
7. Comprobación de salud final.

La recuperación pendiente tiene prioridad sobre
cualquier nueva instalación.

La actualización de Tvheadend requiere convergencia entre
las URL de la playlist local y los mux del servidor.

Se comprueba convergencia antes y después de preparar
el paquete, antes de iniciar la transacción.

No se utiliza la reconciliación directa de TV46.db
como mecanismo ordinario de mantenimiento PVR.

No se fuerza un reinicio PVR al cambiar la playlist.

La eliminación de huérfanos y conservación de identidad
ante altas, bajas y reapariciones deben verificarse
mediante pruebas funcionales específicas.

## 4. Módulos PVR principales

- pvr_credentials.py: credenciales privadas.
- pvr_playlist.py: plantilla M3U, validación y escritura atómica.
- pvr_playlist_convergence.py: convergencia playlist/mux.
- pvr_epg_settings.py: configuración XMLTV nativa.
- pvr_config.py: configuración HTTP de Tvheadend.
- pvr_http.py: transporte HTTP autenticado.
- update_pvr.py: coordinador y estado final.

La convergencia compara el multiconjunto de URL.
No acredita por sí sola cambios de metadatos,
orden, CUID o identidad individual de canales.

## 5. Actualizador Tvheadend

Selección estricta por arquitectura, versión de CoreELEC,
build exacto, versión del addon, tamaño, SHA256 y ELF.

No se permiten downgrades automáticos.

Estados normales:
- NO_RELEASE
- UP_TO_DATE
- LOCAL_NEWER
- UPDATED

Los estados de aplazamiento no constituyen un fallo
de instalación.

El manifiesto ausente (HTTP 404) produce NO_RELEASE.
Un ZIP ausente o inválido no equivale a NO_RELEASE.

La protección de actividad se aplica a instalaciones
reales, no a simples comprobaciones de versión.

Se conserva la infraestructura transaccional descrita en:
PVR_03_TVHEADEND_UPDATER_2026-11-26.md

## 6. Protección de actividad

- Reproducción activa de Kodi.
- Suscripciones Tvheadend.
- Grabaciones actuales o próximas.
- Actividad de fondo identificable.
- Respuestas inválidas o actividad indeterminada:
  bloqueo preventivo.

La API moderna dispone de status/activity.

Para versiones legacy que devuelven HTTP 404 se consultan
las APIs alternativas de suscripciones, entradas,
grabaciones, planificación y configuración EPG.

La compatibilidad legacy se ha observado en Tvheadend
21.2.3 real, tanto en reposo como en reproducción.

La detección de actividad no constituye una garantía
absoluta frente a carreras o tareas internas no observables.

## 7. Scheduler

Arranque y mantenimiento periódico comparten el coordinador.

Se evita solapar ejecuciones mediante bloqueo.

Se distingue el último intento de la última ejecución
satisfactoria.

Los aplazamientos y fallos respetan el cooldown.

El intervalo configurado se aplica sobre ejecuciones
satisfactorias. Existe reintento diferido cuando procede.

## 8. Arquitectura rclone

Dos procesos raíz:

/storage/.mnt/cloud/1
/storage/.mnt/cloud/2

Cuatro bind:

/storage/.mnt/videos/1
/storage/.mnt/videos/2
/storage/.mnt/tvshows/1
/storage/.mnt/tvshows/2

Las rutas multimedia se mantienen.

Dos configuraciones OneDrive aisladas.
Un escritor OAuth FUSE por cuenta y dispositivo.

MASTER genera y publica MQC2 verificado.
CLIENT recupera configuración bajo las protecciones
de actividad y transacción implementadas.

La biblioteca STRM reside en almacenamiento interno.

La presencia de un montaje no acredita conectividad
remota ni autorización OAuth efectiva.

## 9. Validaciones de laboratorio

PVR-12A:
1748 tests PASS.
Sin ResourceWarning observado en la regresión final.

Candidato integral:
176 archivos.
169 iguales respecto a PVR-09C.
6 modificados.
1 nuevo.

Cloud 2.3.2 ZIP SHA256:
0ca56d0477cf3b34a999590a3eb7f94fdeeb639544cb98ce5823446a2f84a6d2

TAR SHA256:
14004359b0ebd9d69c83d2b0ce8a745a6e682ac4525acc73f97bbd285ffc08f1

Paquete e inventario:
 /tmp/pvr12a-final.bRDkbh

Los directorios temporales son evidencia local,
no dependencias del addon ni parte del repositorio.

## 10. Validación física MASTER

CoreELEC:
21.2.5-Omega_devel_20250919152246

Arquitectura:
Amlogic-ng.arm

Kodi:
21

Cloud:
2.3.2, candidato completo de 176 archivos.

Tvheadend:
21.2.8

Binario SHA256:
6c87ff5c3de2023373b9e36571f5de9848c074cddaafb995bfbd00089712cc80

PVR-12M1:
Instalación integral mediante intercambio atómico.
Rollback anterior conservado.
Kodi reiniciado de forma controlada.
Tvheadend no reiniciado.
PID Tvheadend 3729 conservado.
Montajes y playlist intactos.
PASS.

PVR-12M2:
Reinicio real autorizado tras verificar actividad IDLE.
PASS.

PVR-12M3-R1:
Recuperación temprana: NO_PENDING.
Política de actualización: ALREADY_PROTECTED.
9 servicios activos.
0 unidades fallidas.
0 trabajos systemd pendientes.
PASS.

PVR-12M3-R2:
176 archivos verificados mediante SHA256.
Identidad Tvheadend conservada.
HTTP y HTSP TCP disponibles.
Playlist convergente.
2 FUSE y 4 bind verificados.
2 procesos raíz rclone.
0 servicios legacy activos.
0 transacciones pendientes.
PASS.

Boot ID:
4cab7fd6-4a62-4b81-950a-d4dd08139355

PID Kodi: 4300.
PID Tvheadend: 3745.
PID rclone: 3973 y 3975.

## 11. Persistencia PVR

SQLite TV46.db consultada en modo lectura.

Canales: 714.
Grupos: 54.
Asociaciones: 1428.
PRAGMA quick_check: ok.

SHA256 identidad de canales:
9496740dac9793c0a7dbf51e003bf5c3290df5bfc1080f564996cbac763cf7c0

SHA256 playlist:
baa00e75f08f7c59e73adc97a61c70e4eb82ef5bc2d463245df5579cfe1dfec7

No se realizaron escrituras directas sobre TV46.db.

Las cantidades de grupos y asociaciones se conservaron.
Esta prueba no recalculó los hashes de todas las filas
de grupos y asociaciones.

## 12. Mantenimiento automático MASTER

2026-11-27 00:21:08

status=OK
credentials=UNCHANGED
playlist=UNCHANGED
xmltv_settings=UNCHANGED
tvheadend_update=NO_RELEASE
tvheadend_config=UNCHANGED
health=PASS
failures=[]
deferred=[]

La ausencia del manifiesto publicado permite completar
el mantenimiento ordinario sin actualizar Tvheadend.

## 13. Catálogo STRM

Archivos activos observados antes y después del reinicio:

Películas: 786 -> 786.
Episodios: 1015 -> 1015.

La generación posterior en staging registró:
788 películas y 1016 episodios.

El publicador indicó ausencia de catalog.zip pendiente.

La diferencia entre los contadores de staging y los
archivos activos requiere una lectura posterior a la
finalización del catálogo.

No se acredita equivalencia exacta de contenido a partir
de cantidades exclusivamente.

## 14. Estado CLIENTE

CoreELEC 21.2.5, Amlogic-ng.arm.
Cloud 2.3.2 anterior.
Tvheadend 21.2.3.
pvr.hts 21.2.6.1.

PVR-12B1:
Transferencia de ambos paquetes PASS.

PVR-12B2:
2 FUSE + 4 bind PASS.
176 archivos candidatos verificados.
6 modificados y 1 nuevo respecto al addon activo.

PVR-12B3:
Selección UPDATE_AVAILABLE.
Validación ZIP Tvheadend 21.2.8 PASS.

PVR-12B4:
DEFERRED_KODI_PLAYBACK.
DEFERRED_TVH_SUBSCRIPTIONS.
Instalación no ejecutada.
Servicios no reiniciados.
Kodi PID 4396 y Tvheadend PID 3821 conservados.

La decisión de aplazar es correcta y esperada.

El CLIENTE queda fuera de nuevas intervenciones hasta
disponer de autorización y ventana de mantenimiento.

## 15. Rutas de continuidad

MASTER:
/storage/masqelec-backups/PVR-12M.ovEYin

Informes:
- master-install-report.json
- pre-reboot.json
- post-reboot.json
- reboot-baseline.json
- reboot-report.json

Rollback Cloud MASTER:
candidate/service.cloud.masqelec

CLIENTE:
/storage/masqelec-backups/PVR-12B.3fkm3x

Candidato Cloud CLIENTE:
candidate.bb3ilo9_/service.cloud.masqelec

Informes:
- activity-preflight.json
- tvheadend-preflight.json
- candidate-path.txt

Paquetes compilados Ubuntu:
~/GitHub/KodiELEC/target/addons/

## 16. Pendientes reales

- Actualización integral Cloud en CLIENTE.
- Actualización física Tvheadend legacy 21.2.3 -> 21.2.8.
- Instalación y funcionamiento del nuevo grabber nativo.
- Validación física de arquitectura NE.
- Actualización nativa Cloud mediante repositorio Kodi.
- Descarga del release definitivo Tvheadend desde GitHub.
- Prueba de corte físico durante una transacción.
- Revocación OAuth real y recuperación.
- Validación posterior a cambios reales de playlist:
  altas, bajas, reapariciones y eliminación de huérfanos.
- Confirmación del catálogo activo tras terminar su staging.

El MASTER mantiene el grabber personalizado anterior.
No se fuerza una reinstalación de Tvheadend 21.2.8
para cambiarlo artificialmente.

No se consideran superados los pendientes utilizando
resultados de laboratorio o pruebas de versiones anteriores.

## 17. Forma de trabajo

- Inspeccionar antes de modificar.
- Trabajar en develop.
- Laboratorios separados de producción.
- Agrupar pruebas relacionadas para reducir iteraciones.
- Entregar comandos reproducibles para Ubuntu y SSH.
- Registrar resultados reales y causas de cada fallo.
- Conservar evidencias históricas.
- Regresión completa después de cambios funcionales.
- No modificar /system.
- No escribir directamente TV46.db.
- Excepción controlada: política individual Addons33.db
  durante arranque temprano y con respaldo.
- No divulgar credenciales, tokens ni playlist privada.
- No detener reproducción de terceros.
- No publicar paquetes sin autorización del operador.
- No confundir commit de código con distribución de release.

## 18. Siguiente paso

Revisar diff y documentación.
Ejecutar regresión final.
Consolidar commit en develop.

El operador mantiene el control de la publicación
de los paquetes y manifiestos de producción.
