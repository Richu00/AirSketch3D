@echo off
cd /d "%~dp0"
if not exist backend\venv\Scripts\python.exe (
    echo Run start_backend.bat once first to create the virtual environment.
    pause
    exit /b 1
)
call backend\venv\Scripts\activate.bat
python -m pytest -q backend\tests
pause
