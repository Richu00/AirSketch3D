@echo off
setlocal EnableExtensions
title AIRCONTROL Launcher
cd /d "%~dp0"

echo [AIRCONTROL] Starting backend ...
start "AIRCONTROL BACKEND" cmd /k ""%~dp0start_backend.bat""

echo [AIRCONTROL] Waiting for backend on http://127.0.0.1:8000 (first run installs packages, up to 5 min) ...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 300;$i++){ try{ $r=Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 1; if($r.ok){$ok=$true;break} }catch{}; Start-Sleep -Seconds 1 }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
    echo [AIRCONTROL] Backend did not start - read the BACKEND window for the error.
    pause
    exit /b 1
)

echo [AIRCONTROL] Backend is up. Starting frontend ...
start "AIRCONTROL FRONTEND" cmd /k ""%~dp0start_frontend.bat""
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:5173
