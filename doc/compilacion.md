# Compilación

`build.bat` crea un ejecutable independiente, `dist\BtScanner.exe`. En el equipo donde se use ese archivo no hace falta tener Python.

## Requisitos

- Windows 10 u 11.
- Python 3.10 o superior, disponible como `python` en `PATH`. La instalación de python.org incluye Tk, que es la ventana del programa.
- Conexión a internet la primera vez, para instalar las proyecciones de Windows y PyInstaller dentro de un entorno virtual.

Comprueba Python con:

```bat
python --version
```

## Compilar

Desde la carpeta del proyecto:

```bat
build.bat
```

El script hace esto, en orden:

1. Ejecuta las pruebas (`python -m unittest discover -s tests -t .`). Si fallan, no compila.
2. Crea `.venv` si todavía no existe.
3. Instala lo indicado en `requirements.txt` y PyInstaller.
4. Empaqueta `main.py` en un solo archivo, sin consola.

Al terminar, el ejecutable queda en:

```text
dist\BtScanner.exe
```

Si abres `build.bat` con doble clic, la ventana espera una tecla al final para que puedas leer el resultado. Desde una consola puedes evitar esa pausa:

```bat
build.bat --nopause
```

Puedes borrar `.venv`, `build` y `dist` cuando quieras. El script vuelve a crear lo que necesite.

## Problemas frecuentes

**`No se encontro Python en PATH`.** Instala Python desde python.org y márcalo para añadirlo al `PATH`.

**Windows SmartScreen avisa al abrir el `.exe`.** El archivo no está firmado. Si lo compilaste tú, en el aviso elige más información y después ejecutar de todas formas.

**La primera ejecución tarda varios segundos.** Es el desempaquetado del modo de un solo archivo. Después se abre la ventana.
