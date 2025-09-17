@echo off
setlocal
:: Set the root directory (C:\Daggerwalk)
set SCRIPT_DIR=C:\Daggerwalk\DaggerwalkBot

:: Check if Daggerfall Unity is already running
tasklist /fi "imagename eq DaggerfallUnity.exe" 2>NUL | find /i "DaggerfallUnity.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo Daggerfall Unity is already running. (Supervisor will handle readiness.) 
    :: Do NOT exit here; we always start the supervisor so it can manage DFU/bot.
)

:: Define the Python executable path (assuming it's in the same directory)
set PYTHON_EXECUTABLE="%SCRIPT_DIR%\daggerwalk_venv\Scripts\python.exe"
:: Prefer pythonw.exe to avoid a console window if available
set PYTHONW_EXECUTABLE="%SCRIPT_DIR%\daggerwalk_venv\Scripts\pythonw.exe"
if exist %PYTHONW_EXECUTABLE% (
    set PYTHON_EXECUTABLE=%PYTHONW_EXECUTABLE%
)

:: Run the Python script
%PYTHON_EXECUTABLE% "%SCRIPT_DIR%\start_daggerwalk.py"

:end
endlocal
