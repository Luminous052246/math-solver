@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Start the web UI on all interfaces so phones/tablets on the same LAN can connect.
set "PY="
call :try "%MATH_SOLVER_PYTHON%"
if defined PY goto run
call :try "python"
if defined PY goto run
call :try "D:\miniconda\envs\MyPytorch\python.exe"
if defined PY goto run

echo.
echo [ERROR] No Python with sympy/z3 found.
echo Install them first:  pip install -r requirements.txt
echo Or set MATH_SOLVER_PYTHON to your python.exe path.
echo.
pause
exit /b 1

:run
echo Starting Math Solver (LAN mode) with: %PY%
echo Open the LAN URL printed below on your phone/tablet (same Wi-Fi).
echo Close this window or press Ctrl+C to stop the server.
echo.
"%PY%" webapp.py --host 0.0.0.0 %*
echo.
pause
exit /b 0

:try
if "%~1"=="" exit /b 0
"%~1" -c "import sympy, z3" >nul 2>nul
if not errorlevel 1 set "PY=%~1"
exit /b 0
