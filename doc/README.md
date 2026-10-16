# Escáner Bluetooth

Programa de Windows que muestra los dispositivos Bluetooth cercanos y los ya emparejados, con el mismo tipo de ventana que el escáner Wi-Fi.

La tabla indica estado, señal, nombre, dirección, tipo (BLE, clásico o dual), clase y servicios. Al elegir una fila, el panel inferior muestra el detalle. Desde ahí se puede emparejar, olvidar, conectar y desconectar.

Emparejar usa el cuadro de Windows, que puede pedir un PIN. Conectar un dispositivo clásico activa los servicios que Windows ya instaló (audio, manos libres, HID). Conectar un dispositivo BLE abre una sesión GATT que dura mientras el programa sigue abierto. Desconectar hace la operación inversa.

## Requisitos

- Windows 10 u 11.
- Un adaptador Bluetooth encendido.
- Python 3.10 o superior, con Tk, para ejecutarlo desde el código.

El barrido de dispositivos cercanos usa las API de Bluetooth de Windows. En algunos equipos la lista BLE queda vacía si la ubicación del sistema está desactivada.

## Ejecutar desde el código

En la carpeta del proyecto:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

También vale `.venv\Scripts\python -m bt_scanner`.

## Documentación

- [compilacion.md](compilacion.md): cómo generar `BtScanner.exe`.
- [uso.md](uso.md): la ventana, el detalle y la conexión.
