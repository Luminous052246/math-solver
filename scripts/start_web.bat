@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

rem Prefer an explicit interpreter, then the project virtual environment, then python on PATH.
set "PY="
call :try "%MATH_SOLVER_PYTHON%"
if defined PY goto run
call :try "%~dp0..\.venv\Scripts\python.exe"
if defined PY goto run
call :try "python"
if defined PY goto run

echo.
echo [ERROR] No Python with sympy and z3 found.
echo Create one from this directory:
echo   python -m venv .venv
echo   .venv\Scripts\python -m pip install -r requirements.txt
echo Or set MATH_SOLVER_PYTHON to that interpreter.
echo.
pause
exit /b 1

:run
echo Starting Math Solver web UI with: %PY%
echo Add --host 0.0.0.0 to listen on the LAN. Other arguments are passed through.
echo Press Ctrl+C to stop the server.
echo.
"%PY%" webapp.py %*
echo.
pause
exit /b 0

:try
if "%~1"=="" exit /b 0
"%~1" -c "import sympy, z3" >nul 2>nul
if not errorlevel 1 set "PY=%~1"
exit /b 0
