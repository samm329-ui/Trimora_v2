@echo off
setlocal enabledelayedexpansion
title Trimora Launcher

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

echo ================================================================
echo   Trimora -- pre-flight checks
echo ================================================================
echo(

echo   [*] Checking Python ...
where python >nul 2>&1
if errorlevel 1 (
    echo   [X] Python not found -- install Python 3.10+
    pause
    exit /b 1
)
python --version
echo   [V] Python found
echo(

echo   [*] Checking Node.js ...
where node >nul 2>&1
if errorlevel 1 (
    echo   [X] Node.js not found -- install Node.js 18+
    pause
    exit /b 1
)
node --version
echo   [V] Node.js found
echo(

echo   [*] Virtual environment ...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   [*] Creating venv ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   [X] Failed to create venv
        pause
        exit /b 1
    )
    echo   [V] Venv created
) else (
    echo   [V] Venv exists
)
echo(

echo ================================================================
echo   Installing backend packages
echo ================================================================
echo(
"%VENV_DIR%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    echo   [X] pip install failed
    pause
    exit /b 1
)
echo   [V] Backend deps installed
echo(

echo ================================================================
echo   Frontend packages
echo ================================================================
echo(
if not exist "%FRONTEND_DIR%\node_modules" (
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        popd
        echo   [X] npm install failed
        pause
        exit /b 1
    )
    popd
    echo   [V] Frontend deps installed
) else (
    echo   [V] node_modules exists
)
echo(

echo ================================================================
echo   FFmpeg check
echo ================================================================
echo(
set "FFMPEG_OK=no"
where ffmpeg >nul 2>&1
if not errorlevel 1 set "FFMPEG_OK=yes"

if "!FFMPEG_OK!"=="no" (
    echo   [!] FFmpeg not found in PATH.
    echo   [!] Some audio features will be disabled.
    echo   [!] Install manually from https://ffmpeg.org/download.html
    echo(
)

echo   [V] Proceeding without FFmpeg
echo(

echo ================================================================
echo   Launching services
echo ================================================================
echo(

echo   [*] Starting backend ...
start "Trimora Backend" /D "%ROOT%" "%VENV_DIR%\Scripts\python.exe" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
echo   [V] Backend on http://localhost:8000
timeout /t 2 /nobreak >nul

echo   [*] Starting frontend ...
start "Trimora Frontend" /D "%FRONTEND_DIR%" cmd /k "npx vite --host 0.0.0.0 --port 5173"
echo   [V] Frontend on http://localhost:5173
echo(

echo   [V] Trimora running
echo   [*] Backend  -- http://localhost:8000
echo   [*] Frontend -- http://localhost:5173
echo(
pause
exit /b 0
