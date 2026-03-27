@echo off
echo ============================================================
echo  Angel One Data Availability Test
echo  Output will be saved to: tools\angel_one_report.txt
echo ============================================================
echo.

cd /d "%~dp0..\backend"

if not exist "venv\Scripts\python.exe" (
    echo ERROR: backend\venv not found.
    echo Run this from the project root first:
    echo   cd backend ^&^& python -m venv venv ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

venv\Scripts\python.exe ..\tools\test_angel_data.py

echo.
echo ============================================================
echo  Done. Check tools\angel_one_report.txt for full results.
echo ============================================================
pause
