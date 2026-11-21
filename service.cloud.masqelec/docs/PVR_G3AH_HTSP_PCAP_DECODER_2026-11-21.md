# G3-AH — PCAP → TCP → HTSP (2026-11-21)

## Objetivo y evidencia previa

El ensayo G3-AD reprodujo `TVH Alpha Renamed` / `Kodi Alpha` durante 40 muestras, sin cambio de UUID TVH ni IDs Kodi. En G3-AF se capturaron 28 paquetes TCP **sin payload** durante el renombrado. Una captura posterior durante reproducción tuvo 1501 paquetes, **1024 con payload**, y terminó con Kodi actualizado a `Alpha Renamed` e IDs 3/2.

En el PCAP playback, inspección de cadenas por puerto de cliente mostró `channelAdd` y `channelName` (2 apariciones cada uno) en nuevas conexiones **49262** y **40098**, ninguna en conexión antigua 46266. Se comprobó apertura/cierre TCP. Esta evidencia es fuerte, pero textual: G3-AH incorpora un analizador real de mensajes binarios.

## Formato verificado desde código fuente

Tvheadend `src/htsmsg_binary.c` y `src/htsmsg.h` en rama master:
- Mensaje HTSP: 4 bytes big-endian con longitud del mapa serializado y luego los campos.
- Cada campo: `tipo:uint8`, `largo_nombre:uint8`, `largo_valor:uint32 big-endian`, nombre en bytes y valor.
- Tipos `HMF_MAP=1`, `HMF_S64=2`, `HMF_STR=3`, `HMF_BIN=4`, `HMF_LIST=5`, `HMF_BOOL=7`, `HMF_UUID=8`.
- Campo `method` contiene `channelAdd`, `channelUpdate`, etc. `channelId` es identificador HTSP, **no** `PVR.GetChannels.channelid` y no equivale a `CUID`.
- Referencias: https://github.com/tvheadend/tvheadend/blob/master/src/htsmsg_binary.c y https://github.com/tvheadend/tvheadend/blob/master/src/htsmsg.h

## Implementación

`tools/pvr_g3ah_htsp_pcap.py` lee PCAP clásico (Ethernet/IPv4/TCP) **offline**, sin librerías de terceros; solo el puerto del laboratorio 19992. Verifica cabeceras, longitud de mensajes, tipos de campos, límites de tamaño, reensambla TCP en orden de secuencia, descarta retransmisiones ya recibidas, aborta decodificación del flujo si detecta hueco/desalineación. Separa sesiones por puerto de cliente y dirección. Para flujos con captura iniciada a mitad de conexión **sin SYN**, deliberadamente **no** intenta decodificar HTSP: no inventa límites de frame. Requiere ver handshake inicial para análisis fiable.

Métricas: número de paquetes, paquetes con datos, SYN, paquetes midstream, frames HTSP válidos por sesión, frames inválidos, indicador de hueco, contadores por método allowlist `channelAdd`, `channelUpdate`, `channelDelete`, `subscriptionStart`, `initialSyncCompleted`, etiquetas; flags de presencia `channelName`/`channelId`, nunca valores.

Seguridad: no imprime contenido de mensajes, tokens, IP, URL, contraseñas ni datos de streaming. El archivo bruto **no se copia ni sube** a GitHub. Tamaño de captura limitado a 32 MiB; framing por mensaje hasta 4 MiB; límites de anidamiento y campos.

Limitaciones explícitas:
- Puede no detectar mensajes de un flujo iniciado antes de la captura; las sesiones del playback con SYN sí son analizables.
- Los segmentos TCP fuera de orden producen `gap_or_desync=True`, no falsas evidencias de ausencia de evento. No reconstruye conversaciones tras pérdidas; no garantiza ausencia de tráfico en interfaces distintas.
- `initialSyncCompleted` puede ser frecuente o inexistente según backend; la decodificación solo informa lo observado.
- Es una herramienta de laboratorio, no un componente de producción; no modifica `pvr.hts`, Kodi, TVH ni SQLite.
- La captura puede incluir datos privados pese a que el reporte no los muestra. No subir el archivo ni ejecutarlo contra tráfico de producción.
- El módulo no reconstruye una sesión que cambia de conexión conservando el mismo puerto tras cierre si no se ve un SYN nuevo, ni soporta IPv6/VLAN/pcapng: casos fuera de alcance del lab.

## Pruebas y ejecución en Ubuntu

Se prepararon **12 tests sintéticos** en `tests/test_pvr_g3ah_htsp_pcap.py` (formato binario, secreto oculto, campo inválido, Ethernet TCP, segmentación, retransmisión, gap, end-to-end, PCAP inválido, ausencia de payload). **Validación local de una implementación equivalente 12/12 PASS** antes de subir los archivos; la versión exacta en GitHub debe ejecutarse en Ubuntu por operador y confirmarse. No declarar gate Ubuntu PASS hasta ver salida.

```bash
cd /home/ubuntu/GitHub/service.cloud.masqelec
git pull --ff-only origin develop
python3 -m unittest discover -s service.cloud.masqelec/tests -p 'test_pvr_g3ah_htsp_pcap.py' -v
cd service.cloud.masqelec/lab/pvr_g3ab
sudo python3 ../../tools/pvr_g3ah_htsp_pcap.py runtime/htsp_capture/g3af_rename.pcap
sudo python3 ../../tools/pvr_g3ah_htsp_pcap.py runtime/htsp_capture/g3af_playback.pcap
```

Para la ruta desde `lab/pvr_g3ab`, `../../tools/` llega al directorio `service.cloud.masqelec/tools/`.

Si se obtienen `channelAdd` válidos sobre 49262 y 40098 servidor→Kodi, habremos probado que esa sincronización entrega inventario del backend. Aun así no demostraría cuál fue el trigger que provocó la reconexión ni si TVH omitió `channelUpdate` de manera general. Si el parser devuelve `gap_or_desync` o cero frames a pesar de texto `channelAdd`, **no inferir ausencia de mensajes**: investigar límites/captura con más tests y sin revelar payload.

## Gates

```text
G3AH_SOURCE_PROTO_VERIFIED=YES_TVH_MASTER
G3AH_OFFLINE_DECODER_COMMITTED=YES
G3AH_SYNTHETIC_TESTS_PREPARED=12
G3AH_UBUNTU_UNIT_TESTS=PENDING
G3AH_RENAME_PCAP_DECODE=PENDING
G3AH_PLAYBACK_PCAP_DECODE=PENDING
G3AH_CHANNELADD_FRAME_VALIDATED=PENDING
G3AH_HTSP_CHANNELUPDATE_PUSH_DURING_REFETCH=UNPROVEN
G3AH_PRODUCTION_TOUCHED=NO
```
