@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   WorkBrief Web
echo   Open http://localhost:8600 in your browser
echo   Close this window to stop the server
echo ========================================
echo.

python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8600

if errorlevel 1 (
    echo.
    echo Failed to start. Check Python and run: pip install -r requirements.txt
    pause
)
