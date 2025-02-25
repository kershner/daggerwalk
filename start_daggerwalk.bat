@echo off
setlocal

:: Set the root directory (C:\Daggerwalk)
set SCRIPT_DIR=C:\Daggerwalk\DaggerwalkBot

:: Define the Python executable path (assuming it's in the same directory)
set PYTHON_EXECUTABLE="%SCRIPT_DIR%\daggerwalk_venv\Scripts\python.exe"

:: Run the Python script
%PYTHON_EXECUTABLE% "%SCRIPT_DIR%\start_daggerwalk.py"

:: Start the Twitch bot separately
%PYTHON_EXECUTABLE% "%SCRIPT_DIR%\daggerwalk_twitch_bot.py"

endlocal
