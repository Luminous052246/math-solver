@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Find a Python interpreter that has sympy and z3.
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
echo Starting Math Solver web UI with: %PY%
echo Close this window or press Ctrl+C to stop the server.
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
