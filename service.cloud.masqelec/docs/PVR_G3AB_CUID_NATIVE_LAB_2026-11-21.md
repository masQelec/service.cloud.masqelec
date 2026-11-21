# G3-AB — laboratorio independiente para persistencia de identidad CUID (2026-11-21)

## Alcance

G3-AA dispone de **15 pruebas offline PASS**. El formato actual de la playlist remota fue inspeccionado en la rama predeterminada de `masQelec/cloud.masqelec`: 865 `#EXTINF`, 865 `CUID` presentes y únicos; no confundir con la observación histórica de 720 canales en master. G3-Z5 ha demostrado que un servicio inactivo sin canal puede compartir mux con servicios de canales existentes. Ninguno de esos resultados demuestra que TVH interprete CUID ni que Kodi lo preserve.

G3-AB usa el nuevo directorio `lab/pvr_g3ab` con:
- Compose **nuevo proyecto** `masqelec-pvr-g3ab`, puertos HTTP/HTSP **solo loopback 19991/19992**, otro `runtime/tvh_config` totalmente separado de G3-W, Nginx de streams sintéticos y sin volúmenes de master.
- `prepare.py` escribe únicamente `lab/pvr_g3ab/runtime/playlist/playlist.m3u` con dos CUID estables `g3ab-001` y `g3ab-002` en atributos `CUID` entrecomillados; nombres, grupos y URL son sintéticos.
- Alternativa `ch1-alt.ts` es una copia del mismo TS, pero cambia la URL en la M3U; evita cambiar a la vez el contenido audiovisual y la URL.
- Seis variaciones con CUID idénticos y un estado restaurado.
- `tests/test_pvr_g3ab_fixture.py`: 16 casos sintéticos. **No declarar PASS antes de que Ubuntu los ejecute**.

## Etapas independientes

Cada etapa parte de los atributos de **baseline** y cambia una única dimensión, salvo `restored` que la restaura completamente:

| Etapa | Acción | Expectativa de prueba, aún NO demostrada |
| --- | --- | --- |
| `baseline` | Dos canales con CUID distintos | Registrar UUID TVH y channelid Kodi |
| `rename` | Renombrar el primero | Comprobar UUID/IDs y nombre |
| `url` | Cambiar la URL del primero | Comprobar si se regenera mux, servicio y/o canal |
| `group` | Cambiar grupo del primero | Comprobar categorías y grupo original |
| `reorder` | Invertir orden M3U sin cambiar `tvg-chno` | Comprobar numeración y IDs, sin asumir reorder Kodi |
| `homonym` | Ambos nombres iguales, CUID distintos | Observar si TVH confunde o conserva dos identidades |
| `restored` | M3U idéntica a `baseline` | Comprobar si identificadores recuperan estado |

## Preparación Ubuntu

Ejecutar comandos **solo** en Ubuntu de laboratorio:

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m py_compile service.cloud.masqelec/lab/pvr_g3ab/prepare.py
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ab_fixture.py' -v

cd service.cloud.masqelec/lab/pvr_g3ab
docker compose config --quiet
python3 prepare.py baseline
docker compose up -d
docker compose ps
```

TVH G3-AB en `http://127.0.0.1:19991`. Crear red Automatic IPTV **exclusiva** para el laboratorio G3-AB apuntando a `file:///lab_playlist/playlist.m3u`, configurar su refetch y mapeo de servicios, y comprobar dos canales. No conectar este TVH a producción.

**Kodi:** usar `runtime/kodi_home` como perfil separado y configurar `pvr.hts` para conectar **solo a 127.0.0.1:19992**. No abrir G3-W Kodi y G3-AB Kodi simultáneamente; pueden competir por servidor web puerto 8080 o por el perfil activo. Aislar también la configuración HTTP; si se habilita JSON-RPC HTTP, proteger el acceso: previamente se observó que Kodi abría `0.0.0.0:8080` y `[::]:8080`. No asumir que establecer `HOME` prueba aislamiento absoluto del perfil; verificar rutas reales de userdata y la conexión pvr.hts antes de proceder. Pueden utilizarse puertos HTTP diferentes, pero no se da por configurado un 8081 inexistente.

## Validación funcional, por etapas

1. Registrar **baseline** de canal TVH (UUID, nombre sintético, servicios) por `http://127.0.0.1:19991/api/channel/grid` y Kodi con `PVR.GetChannels` vía su JSON-RPC de lectura.
2. Cambiar `python3 prepare.py rename`; **esperar relectura efectiva**, volver a obtener ambas listas, comparar UUID/IDs. Si no cambia el nombre, no asumir que TVH ignora CUID: distinguir refresco fallido.
3. Repetir por separado `url`, `group`, `reorder`, `homonym`, **`restored`**, registrando los IDs y qué atributos cambiaron. La salida de `prepare.py` confirma solo el nuevo archivo.
4. Ante identificación ambigua, desaparición de canales, errores de TVH o Kodi, parar el gate y conservar snapshots. No limpiar SQLite ni manipular servicios/muxes.
5. No afirmar que CUID es soportado por TVH hasta que exista evidencia específica de lectura de dicho atributo; estabilidad de UUID ante modificaciones es solo comportamiento observado, no causalidad CUID.

`G3AB_LAB_CREATED=YES`; `G3AB_UNIT_TESTS=PENDING`; `G3AB_NATIVE_IDENTITY=NOT_TESTED`; `CUTOVER_AUTHORIZED=NO`; `PRODUCTION_TOUCHED=NO`.


## Arranque inicial comunicado por el operador — 2026-11-21

```text
G3AB_STAGE=BASELINE
G3AB_CUID_COUNT=2
G3AB_MASTER_UNTOUCHED=YES
G3AB_G3W_UNTOUCHED=YES
Docker network masqelec-pvr-g3ab_pvr_g3ab created
masqelec-pvr-g3ab-streams-1 Up (80/tcp interno)
masqelec-pvr-g3ab-tvh-1 Up (127.0.0.1:19991->9981/tcp, 127.0.0.1:19992->9982/tcp)
```

Estado `G3AB_COMPOSE_STARTED=YES`, `G3AB_BASELINE_FILE_WRITTEN=YES`, `G3AB_UNIT_TESTS=NOT_REPORTED`, `G3AB_TVH_CHANNELS=NOT_YET_VERIFIED`, `G3AB_KODI_CHANNELS=NOT_YET_VERIFIED`. Puertos publicados en localhost, sin evidencia de lectura efectiva por TVH o mapeo a canales. Siguiente paso: configurar Automatic IPTV apuntando exclusivamente a `file:///lab_playlist/playlist.m3u`, mapear dos servicios, consultar el baseline de TVH por API y luego conectar perfil Kodi aislado. No ejecutar etapa `rename` antes de registrar ambos snapshots.
