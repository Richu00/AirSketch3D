@echo off
setlocal EnableExtensions
title AIRCONTROL Frontend
cd /d "%~dp0frontend"
if not exist node_modules (
    echo [AIRCONTROL] Installing frontend packages ...
    call npm install
    if errorlevel 1 (
        echo [AIRCONTROL] ERROR: npm install failed. Is Node.js installed?
        pause
        exit /b 1
    )
)
call npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
pause
