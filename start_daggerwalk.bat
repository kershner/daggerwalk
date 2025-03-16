@echo off
setlocal
:: Set the root directory (C:\Daggerwalk)
set SCRIPT_DIR=C:\Daggerwalk\DaggerwalkBot

:: Check if Daggerfall Unity is already running
tasklist /fi "imagename eq DaggerfallUnity.exe" 2>NUL | find /i "DaggerfallUnity.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo Daggerfall Unity is already running. Exiting...
    goto :end
)

:: Define the Python executable path (assuming it's in the same directory)
set PYTHON_EXECUTABLE="%SCRIPT_DIR%\daggerwalk_venv\Scripts\python.exe"
:: Run the Python script
%PYTHON_EXECUTABLE% "%SCRIPT_DIR%\start_daggerwalk.py"

:end
endlocal