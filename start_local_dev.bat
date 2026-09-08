@echo off
setlocal

set "DAGGERWALK_ROOT=%~dp0"
if not defined DAGGERWALK_SITE_DIR set "DAGGERWALK_SITE_DIR=C:\Programming\kershner_org"
if not "%~1"=="" set "DAGGERWALK_DEV_USER=%~1"
set "DAGGERWALK_DEV_SERVER=http://127.0.0.1:8000"

if not exist "%DAGGERWALK_SITE_DIR%\manage.py" (
    echo Local Django site not found at %DAGGERWALK_SITE_DIR%
    echo Set DAGGERWALK_SITE_DIR if it is stored elsewhere.
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Start Rancher Desktop, then try again.
    exit /b 1
)

docker inspect daggerwalk-redis >nul 2>&1
if errorlevel 1 (
    docker run -d --name daggerwalk-redis -p 127.0.0.1:6379:6379 redis:7-alpine
) else (
    docker start daggerwalk-redis >nul
)
if errorlevel 1 exit /b 1

:: Some Docker Desktop/Rancher setups create the container before attaching its
:: default bridge. Connecting again is harmless when it is already attached.
docker network connect bridge daggerwalk-redis >nul 2>&1
powershell.exe -NoProfile -Command "$limit=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $limit) { $client=[Net.Sockets.TcpClient]::new(); try { $client.Connect('127.0.0.1', 6379); $client.Dispose(); exit 0 } catch { $client.Dispose(); Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 (
    echo Redis is running but did not become reachable at 127.0.0.1:6379.
    docker logs --tail 20 daggerwalk-redis
    exit /b 1
)

pushd "%DAGGERWALK_SITE_DIR%"
set "DJANGO_SETTINGS_MODULE=site_config.settings.dev"
call .\venv\Scripts\python.exe manage.py migrate
if errorlevel 1 goto :failed

start "Daggerwalk Django" cmd /k ".\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
start "Daggerwalk Cache Worker" cmd /k ".\venv\Scripts\celery.exe -A kershner worker --pool=solo --loglevel=info"
popd

powershell.exe -NoProfile -Command "$limit=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $limit) { try { Invoke-WebRequest http://127.0.0.1:8000/daggerwalk/ -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 (
    echo Django did not become ready at http://127.0.0.1:8000
    exit /b 1
)

start "Daggerwalk Bot" cmd /k call "%DAGGERWALK_ROOT%start_daggerwalk.bat" --mode dev
powershell.exe -NoProfile -Command "$limit=(Get-Date).AddMinutes(5); while ((Get-Date) -lt $limit) { try { Invoke-WebRequest http://127.0.0.1:5050/ -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
    echo The Daggerwalk controls did not become ready at http://127.0.0.1:5050
    exit /b 1
)

start "" http://127.0.0.1:8000/daggerwalk/
start "" http://127.0.0.1:5050/
exit /b 0

:failed
popd
exit /b 1
