@echo off
setlocal

:: ============================================================
:: run_pipeline.bat
:: Runs the full fantasy baseball Statcast pipeline and logs
:: all output (stdout + stderr) to logs\pipeline_YYYY-MM-DD.log
::
:: Log location : C:\Users\dusti\fantasy-baseball\logs\
:: Retention    : 30 days (older logs deleted automatically)
:: ============================================================

set PROJECT_DIR=C:\Users\dusti\fantasy-baseball
set PYTHON=C:\Users\dusti\AppData\Local\Python\pythoncore-3.14-64\python.exe
set LOG_DIR=%PROJECT_DIR%\logs

:: Create log directory if it doesn't exist
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Build a datestamped log filename using PowerShell (locale-independent)
for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set LOG_DATE=%%d
set LOG_FILE=%LOG_DIR%\pipeline_%LOG_DATE%.log

:: Rotate logs: delete any logs older than 30 days
forfiles /p "%LOG_DIR%" /s /m *.log /d -30 /c "cmd /c del @path" 2>nul

:: ============================================================
:: Run
:: ============================================================
echo ============================================================ >> "%LOG_FILE%"
echo Run started: %DATE% %TIME% >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

"%PYTHON%" "%PROJECT_DIR%\run_pipeline.py" >> "%LOG_FILE%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo. >> "%LOG_FILE%"
if %EXIT_CODE% == 0 (
    echo Run completed successfully: %DATE% %TIME% >> "%LOG_FILE%"
) else (
    echo RUN FAILED with exit code %EXIT_CODE%: %DATE% %TIME% >> "%LOG_FILE%"
)
echo ============================================================ >> "%LOG_FILE%"

:: On success, start the HTTP server (if not already running) and open the dashboard
if %EXIT_CODE% == 0 call "%PROJECT_DIR%\launch_dashboard.bat"

exit /b %EXIT_CODE%
