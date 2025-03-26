@echo off
setlocal

:: Set absolute paths to avoid issues with current directory when running as admin
set SCRIPT_DIR=C:\Daggerwalk\DaggerwalkBot
set PYTHON_EXECUTABLE=%SCRIPT_DIR%\daggerwalk_venv\Scripts\python.exe
set MONITOR_SCRIPT=%SCRIPT_DIR%\daggerwalk_bot_monitor.py

:: Verify files exist before executing
if not exist "%PYTHON_EXECUTABLE%" (
    echo ERROR: Python executable not found at %PYTHON_EXECUTABLE%
    goto end
)

if not exist "%MONITOR_SCRIPT%" (
    echo ERROR: Monitor script not found at %MONITOR_SCRIPT%
    goto end
)

:: Change to the script directory before execution
cd /d "%SCRIPT_DIR%"
echo Current directory: %CD%

:: Run the script
echo Starting monitor script...
"%PYTHON_EXECUTABLE%" "%MONITOR_SCRIPT%"

:end
endlocal