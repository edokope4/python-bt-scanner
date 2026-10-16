@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Compila BtScanner.exe con PyInstaller en un solo archivo.
REM Uso: build.bat
REM      build.bat --nopause

where python >nul 2>&1
if errorlevel 1 (
    echo No se encontro Python en PATH.
    echo Instala Python 3.10 o superior y vuelve a ejecutar este script.
    exit /b 1
)

echo Ejecutando pruebas...
python -m unittest discover -s tests -t .
if errorlevel 1 (
    echo Las pruebas fallaron. No se compila el ejecutable.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

set "PY=%~dp0.venv\Scripts\python.exe"

echo Instalando dependencias y PyInstaller...
"%PY%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt" pyinstaller
if errorlevel 1 (
    echo No se pudieron instalar las dependencias.
    exit /b 1
)

echo Compilando dist\BtScanner.exe ...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name BtScanner --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" --collect-all winrt --hidden-import winrt.windows.foundation --hidden-import winrt.windows.foundation.collections --hidden-import winrt.windows.devices.bluetooth --hidden-import winrt.windows.devices.bluetooth.advertisement --hidden-import winrt.windows.devices.bluetooth.genericattributeprofile --hidden-import winrt.windows.devices.enumeration --hidden-import winrt.windows.devices.radios --hidden-import winrt.windows.devices.bluetooth.rfcomm --hidden-import winrt.windows.networking --hidden-import winrt.windows.networking.sockets --hidden-import winrt.windows.storage.streams "%~dp0main.py"
if errorlevel 1 (
    echo La compilacion fallo.
    exit /b 1
)

if not exist "%~dp0dist\BtScanner.exe" (
    echo No se genero el ejecutable.
    exit /b 1
)

echo.
echo Listo: %~dp0dist\BtScanner.exe
if /I "%~1"=="--nopause" exit /b 0
pause
exit /b 0
