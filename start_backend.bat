@echo off
setlocal EnableExtensions
title AIRCONTROL Backend
cd /d "%~dp0"

set "VENV=backend\venv"
set "PY=%VENV%\Scripts\python.exe"

rem ---- 1. already running? (start.bat / double-click safe) --------------------
powershell -NoProfile -Command "try{$r=Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2; if($r.service -eq 'AIRCONTROL'){exit 0}else{exit 2}}catch{exit 3}" >nul 2>nul
if %errorlevel%==0 (
    echo [AIRCONTROL] Backend is already running on http://127.0.0.1:8000
    timeout /t 3 >nul
    exit /b 0
)
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue){exit 1}else{exit 0}" >nul 2>nul
if errorlevel 1 (
    echo [AIRCONTROL] ERROR: port 8000 is in use by another program. Close it and try again.
    pause
    exit /b 1
)

rem ---- 2. create / repair the virtual environment -----------------------------
set "NEEDVENV=0"
if not exist "%PY%" set "NEEDVENV=1"
if exist "%PY%" ( "%PY%" -c "import sys" >nul 2>nul || set "NEEDVENV=1" )
if "%NEEDVENV%"=="1" (
    echo [AIRCONTROL] Creating virtual environment in %VENV% ...
    set "BASEPY="
    where py >nul 2>nul && set "BASEPY=py -3"
    if not defined BASEPY ( where python >nul 2>nul && set "BASEPY=python" )
    if not defined BASEPY (
        echo [AIRCONTROL] ERROR: Python 3.10-3.12 was not found. Install it from python.org and tick "Add to PATH".
        pause
        exit /b 1
    )
    %BASEPY% -m venv --clear "%VENV%"
    if errorlevel 1 (
        echo [AIRCONTROL] ERROR: could not create the virtual environment.
        pause
        exit /b 1
    )
)
call "%VENV%\Scripts\activate.bat"

rem ---- 3. install requirements only if something is missing -------------------
python -c "import fastapi, uvicorn, cv2, mediapipe, numpy, pyautogui, pydantic" >nul 2>nul
if errorlevel 1 (
    echo [AIRCONTROL] Installing requirements - first run can take a few minutes ...
    python -m pip install --upgrade pip
    python -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [AIRCONTROL] ERROR: pip install failed. MediaPipe supports Python 3.9-3.12 only - check "python --version".
        pause
        exit /b 1
    )
)

rem ---- 4. start FastAPI / Uvicorn on 127.0.0.1:8000 ---------------------------
echo [AIRCONTROL] Starting backend on http://127.0.0.1:8000  (Ctrl+C to stop)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
echo.
echo [AIRCONTROL] Backend stopped.
pause
