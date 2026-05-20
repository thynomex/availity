@echo off
setlocal

cd /d "%~dp0"

python -m src.cli
set "exit_code=%ERRORLEVEL%"

if not "%exit_code%"=="0" (
    echo.
    echo Application exited with code %exit_code%.
    pause
)

exit /b %exit_code%
