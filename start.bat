@echo off
setlocal
cd /d "%~dp0"

:: 1. Check for uv in PATH or default install locations
set "UV_CMD=uv"
where uv >nul 2>&1
if %ERRORLEVEL% equ 0 goto RUN_UV

if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
    set "UV_CMD=%USERPROFILE%\.cargo\bin\uv.exe"
    goto RUN_UV
)

if exist "%LOCALAPPDATA%\bin\uv.exe" (
    set "UV_CMD=%LOCALAPPDATA%\bin\uv.exe"
    goto RUN_UV
)

:: 2. Fallback to project's virtual environment python
if exist ".venv\Scripts\python.exe" (
    echo Starting photoEditor4sns with .venv Python...
    ".venv\Scripts\python.exe" main.py
    goto END
)

:: 3. Fallback to system python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Starting photoEditor4sns with system Python...
    python main.py
    goto END
)

echo [ERROR] Neither 'uv' nor Python was found.
echo Please install uv or Python to run this application.
pause
exit /b 1

:RUN_UV
echo Starting photoEditor4sns with uv...
"%UV_CMD%" run python main.py
goto END

:END
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application terminated with error code %ERRORLEVEL%.
    pause
)
