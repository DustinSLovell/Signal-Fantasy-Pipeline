@echo off
setlocal

set PROJECT_DIR=C:\Users\dusti\fantasy-baseball
set PYTHON=C:\Users\dusti\AppData\Local\Python\pythoncore-3.14-64\python.exe

cd /d "%PROJECT_DIR%"

:: ── Check if port 8000 is already listening ──────────────────────────────
powershell -NoProfile -Command ^
  "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1

if %errorlevel% == 0 (
    echo   Port 8000 already in use -- dashboard server already running
) else (
    echo   Starting HTTP server on port 8000...
    start "Fantasy Baseball HTTP Server" /min "%PYTHON%" -m http.server 8000
    :: Wait for the server to be ready
    timeout /t 2 /nobreak >nul
)

echo   Opening http://localhost:8000/dashboard.html
start "" "http://localhost:8000/dashboard.html"
