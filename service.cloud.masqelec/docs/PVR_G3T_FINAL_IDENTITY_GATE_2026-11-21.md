# G3-T — Contraste descriptivo canal por canal y criterio final de corte

Fecha 2026-11-21. Rama develop. Código de master y producción inalterados.

## Evidencia ya observada

G3-R: red IPTV LOCAL con URL `file:///storage/.user/playlist.m3u`, `refetch_period=1` minuto, respuesta TVH con propiedades `PARAMS`. Configuración de relectura constatada; evento de relectura no demostrado.

G3-S: dos snapshots a 75 segundos. 720 canales M3U/TVH, 26 grupos deseados, 32 tags TVH y seis históricos sobrantes; UUID y asociaciones en TVH estables. `REFETCH_EVENT_PROVEN=NO` y `KODI_CONVERGENCE_PROVEN=NO`.

## Implementación G3-T

Nuevo `tools/pvr_g3t_identity_crosscheck.py`:
- Solo GET `channeltag/grid` y `channel/grid` y lectura local M3U.
- Compara la multiconjunto de parejas `(nombre del canal NFC, group-title NFC)` extraído del M3U con `(channel.name NFC, tag.name NFC)` de TVH.
- Verifica inventarios completos, UUID de canal sin duplicados, vínculos a tags existentes, cuentas de coincidencias/faltantes/extras y ambigüedades descriptivas.
- Las seis categorías históricas no deseadas no fuerzan un falso error solo por existir; los tags no se borran.
- No imprime nombres, IDs, UUID, rutas ni URLs; muestra exclusivamente contadores y flags.
- 10 pruebas unitarias locales (caso positivo, enlaces ausentes, nombre distinto, tag histórico multiasignado, duplicados ambiguos, grupo M3U inválido, tag inexistente, canal duplicado, NFC y rechazo de endpoint de escritura).

**Lo que NO demuestra este cotejo:** no es una prueba del `CUID` técnico original, no demuestra que TVH haya efectuado una relectura real ni garantiza actualización de bajas en Kodi. Una coincidencia descriptiva completa habilita la siguiente prueba aislada, no el corte en producción.

## Validación agrupada en Ubuntu

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
for name in test_pvr_g3t_identity_crosscheck.py test_pvr_g3s_tvh_two_snapshots.py test_pvr_g3r_tvh_refetch_readonly.py; do
  python3 -m unittest discover -s service.cloud.masqelec/tests -p "$name" -v || break
done
```

Se esperan **30 tests** (10 G3-T, 12 G3-S, 8 G3-R). Confirmar salida del operador antes de registrar PASS.

## Master: una sola ejecución, sin espera de minuto

```bash
scp service.cloud.masqelec/tools/pvr_g3t_identity_crosscheck.py root@192.168.1.102:/storage/.cache/masqelec-g3-audit/
ssh root@192.168.1.102 'python3 /storage/.cache/masqelec-g3-audit/pvr_g3t_identity_crosscheck.py'
```

`MATCH_GATE=PASS` solo significa coincidencia descriptiva total sin duplicados ambiguos. `INCOMPLETE` no debe repararse mediante intervención en TVxx.db ni con eliminación de tags.

## Cierre funcional pendiente (no simularlo)

1. Probar un delta real **en laboratorio aislado**, con M3U de prueba y red TVH de prueba, para demostrar un re-fetch y alta/baja efectiva de un canal **con identidad preservada** sin tocar la M3U del master.
2. Verificar la propagación de bajas a Kodi por PVR nativo/JSON-RPC. Si Kodi no elimina huérfanos, mantener el fallback heredado hasta construir alternativa segura.
3. En `update_pvr.py`, reemplazar el flujo viejo de reinicios/TVxx.db/tag-files **solo después** de gates 1–2. El orquestador API nuevo G3-O no debe convivir con el sincronizador viejo.
4. Ejecutar pruebas integradas y CI, y PR develop→main cuando los gates sean verificables.
5. Mantener seis tags históricos protegidos mientras la propiedad no esté demostrada.

**Estado actual:** `G3T_DESCRIPTIVE_CROSSCHECK_PREPARED=YES`, `G3T_MASTER_RESULT=PENDING`, `G3T_UNIT_TESTS=PENDING`, `LEGACY_CUTOVER=NO`, `API_TAG_WRITES_ACTIVE=NO`, `ZIP_PUBLISHED=NO`.


## Resultado real G3-T (operador) y ajuste de criterio

```text
M3U_CHANNELS=720
TVH_CHANNELS=720
M3U_DISTINCT_NAME_GROUP_PAIRS=707
EXACT_NAME_GROUP_MATCHES=720
MISSING_NAME_GROUP_PAIRS=0
EXTRA_TVH_NAME_GROUP_PAIRS=0
M3U_AMBIGUOUS_DUPLICATE_ENTRIES=24
TVH_MULTITAG_CHANNELS=0
MATCH_GATE=INCOMPLETE
CUID_MAPPING_PROVEN=NO
REFETCH_EVENT_PROVEN=NO
KODI_CONVERGENCE_PROVEN=NO
API_WRITE_EXECUTED=NO
```

**Interpretación:** se han observado las **720/720 coincidencias por multiconjunto nombre+grupo**, sin faltantes ni extras. Las **707 parejas distintas** implican 13 ocurrencias extra por duplicidad descriptiva y 24 entradas pertenecientes a parejas repetidas. No hay evidencia de un error de canal por esos duplicados; la asociación individual por CUID no está demostrada. Las seis categorías históricas siguen protegidas.

**Corrección del instrumento (G3-T v2):** el `MATCH_GATE` se refiere ahora exclusivamente a coincidencia descriptiva completa de multiconjunto. Cuando faltantes/extras son cero y coinciden las cantidades será `PASS`, aunque existan nombres repetidos. La bandera independiente `IDENTITY_DISAMBIGUATION=NOT_PROVEN` conserva el bloqueo de identidad técnica y `CUID_MAPPING_PROVEN=NO` permanece. Un `MATCH_GATE=PASS` **NO autoriza el corte, limpieza Kodi ni fusión de duplicados**.

El operador no confirmó explícitamente los 30 tests del conjunto G3-T/G3-S/G3-R. Tras esta corrección de criterio, debe ejecutarse como mínimo `test_pvr_g3t_identity_crosscheck.py`; ninguna prueba unitaria nueva se declara PASS todavía. Producción intacta.

**Condición de cierre real:** ensayo aislado de refetch con delta de canales; contraste de identidad técnica CUID↔TVH y propagación de bajas a Kodi (preferiblemente mecanismos nativos), y sustitución del escritor heredado antes de conectar API. El resultado real G3-T demuestra coincidencia descriptiva, no resolución de esos tres requisitos.
