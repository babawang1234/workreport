@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   WorkBrief Admin Console
echo   Browser will open http://localhost:8502
echo   Close this window to stop the server
echo ========================================
echo.

python -m streamlit run admin.py --server.port 8502 --server.address localhost

if errorlevel 1 (
    echo.
    echo Failed to start. Check Python and run: pip install -r requirements.txt
    pause
)
