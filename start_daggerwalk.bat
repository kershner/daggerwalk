@echo off
setlocal

:: Root directory is the folder containing this batch file.
set "SCRIPT_DIR=%~dp0"

:: Check if Daggerfall Unity is already running
tasklist /fi "imagename eq DaggerfallUnity.exe" 2>NUL | find /i "DaggerfallUnity.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo Daggerfall Unity is already running. (Supervisor will handle readiness.) 
    :: Do NOT exit here; supervisor still runs
)

:: Always use python.exe (NOT pythonw.exe) so console output is visible
set "PYTHON_EXECUTABLE=%SCRIPT_DIR%daggerwalk_venv\Scripts\python.exe"

:: Launch the supervisor script
echo Starting DaggerWalk supervisor...
"%PYTHON_EXECUTABLE%" "%SCRIPT_DIR%start_daggerwalk.py" %*

echo.
echo ================================================
echo  DaggerWalk supervisor exited.
echo  Press any key to close this window.
echo ================================================
pause >nul

:end
endlocal
