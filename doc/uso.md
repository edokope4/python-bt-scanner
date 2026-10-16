# Uso

Al arrancar se abre una ventana de escritorio. El primer barrido empieza solo.

## La ventana

Arriba está el adaptador: nombre, si el Bluetooth está encendido, dirección local, si admite clásico y BLE, y si el equipo es visible o acepta conexiones.

La tabla lista cada dispositivo:

- **Estado**: «Conectado», «Emparejado» o «Visible». La fila conectada queda resaltada.
- **Señal**, en porcentaje. Sale del RSSI: -40 dBm o mejor es 100 % y -100 dBm o peor es 0 %.
- **Nombre**. Si el dispositivo no lo anuncia, aparece como «Dispositivo sin nombre».
- **Dirección** en formato `AA:BB:CC:DD:EE:FF`.
- **Tipo**: BLE, Clásico o Dual.
- **Clase**: por ejemplo `Audio · Auriculares` o `Periférico · Ratón`, cuando el dispositivo la informa.
- **Servicios**: perfiles anunciados o ya instalados, como batería, audio o HID.
- **Detalle**: fabricante reconocido o si se vio en este barrido.

Al seleccionar una fila, debajo se muestra el detalle: dirección, señal en dBm, clase, fabricante, servicios, si acepta conexión y la última vez que Windows lo vio.

## Conectar y desconectar

Los botones actúan sobre la fila seleccionada.

- **Emparejar** inicia el emparejamiento de Windows. Puede aparecer un PIN o una confirmación. No hace falta aceptar nada dentro de este programa.
- **Olvidar** quita el emparejamiento. Pide confirmación.
- **Conectar** en un dispositivo clásico emparejado activa sus servicios instalados, por ejemplo el audio. En un dispositivo BLE abre una conexión que se mantiene mientras esta ventana sigue abierta.
- **Desconectar** desactiva esos servicios clásicos y cierra la conexión BLE abierta por el programa. Si la consola está abierta sobre ese mismo dispositivo, también cierra el canal de texto. Pide confirmación. Si el dispositivo es un teclado o un ratón, el aviso lo recuerda.
- **Consola** abre una ventana para escuchar lo que envía el dispositivo y probar comandos de texto. No hace falta pulsar Conectar antes: la consola abre ella misma el puerto serie o el UART BLE. Conectar solo activa el perfil de Windows y no muestra los bytes.

Cerrar la ventana suelta las conexiones BLE que abrió el programa y el canal de la consola. Las conexiones clásicas que Windows ya mantiene no se cortan al salir.

**Escanear** pide un barrido nuevo y espera unos segundos. **Repetir cada 15 s** vuelve a hacerlo solo. El buscador y el orden se aplican sobre la última lista, sin otro barrido. También se puede ordenar pulsando el título de Señal, Nombre, Tipo o Estado.

## Consola de desarrollo

Sirve para acordar el protocolo con el sketch antes de escribir la aplicación que manda comandos.

1. Enciende el Arduino y espera a que aparezca en el barrido. Un ESP32 con `BluetoothSerial` o un módulo HC-05/HC-06 se ve como clásico. Un sketch con UART Nordic (servicio `6E400001`) se ve como BLE. Un ESP8266 solo no tiene Bluetooth y no va a aparecer.
2. Selecciona la fila y pulsa **Consola**. El estado de arriba dice si está escuchando el puerto serie o un servicio BLE.
3. Escribe un comando y pulsa **Enviar** o Enter. Por defecto se añade un salto de línea LF, que es lo que suele esperar `readStringUntil('\n')`. CRLF sirve si el sketch lee `\r\n`. «Sin salto» envía el texto tal cual.
4. Lo que llega se escribe en el registro. Lo enviado queda en azul, precedido de `→`.

Empareja el dispositivo antes si Windows aún no conoce el puerto serie. La velocidad de un HC-05 se configura en el módulo (`AT+UART`), no en esta ventana. El texto viaja en UTF-8. Hay una sola consola a la vez.

## Si no aparecen dispositivos

- Confirma que el Bluetooth está encendido y que no estás en modo avión.
- En Configuración, privacidad y ubicación, la ubicación del dispositivo debe estar permitida. Windows la exige para ver anuncios BLE.
- Un dispositivo emparejado puede mostrarse aunque en ese momento no esté anunciando.
- Si conectar un equipo clásico dice que no hay servicios, emparéjalo primero para que Windows instale el perfil.

## Salir

Cierra la ventana.
