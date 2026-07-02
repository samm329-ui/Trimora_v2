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

:: 1. check Python
echo   [*] Checking Python ...
where python >nul 2>&1
if errorlevel 1 (
    echo   [X] Python not found -- install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
python --version
echo   [V] Python found
echo(

:: 2. check Node.js
echo   [*] Checking Node.js ...
where node >nul 2>&1
if errorlevel 1 (
    echo   [X] Node.js not found -- install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)
node --version
echo   [V] Node.js found
echo(

:: 3. virtual environment
echo   [*] Setting up Python virtual environment ...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   [*] Creating virtual environment at %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   [X] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo   [V] Virtual environment created
) else (
    echo   [V] Virtual environment exists
)
echo(

:: 4. pip install
echo ================================================================
echo   Installing backend Python packages
echo ================================================================
echo(
"%VENV_DIR%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    echo   [X] pip install failed -- check your internet connection and requirements.txt
    pause
    exit /b 1
)
echo(
echo   [V] Backend dependencies installed
echo(

:: 5. frontend npm install
echo ================================================================
echo   Installing frontend packages
echo ================================================================
echo(
if not exist "%FRONTEND_DIR%\node_modules" (
    echo   [*] Running: npm install in frontend/
    echo(
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        popd
        echo   [X] npm install failed -- check your internet connection and package.json
        pause
        exit /b 1
    )
    popd
    echo   [V] Frontend dependencies installed
) else (
    echo   [V] node_modules already exists -- skipping
)
echo(

:: 6. FFmpeg check + auto install
echo ================================================================
echo   Checking FFmpeg
echo ================================================================
echo(
where ffmpeg >nul 2>&1
if not errorlevel 1 goto :ffmpeg_ready

echo   [*] FFmpeg not found. Attempting auto-install via winget ...
echo(
echo   Press any key to install FFmpeg via winget, or close this window to cancel.
echo   (winget is built into Windows 10/11 -- no download needed)
echo(
pause

winget install "FFmpeg" --accept-source-agreements --accept-package-agreements >nul 2>&1
if errorlevel 1 (
    echo   [X] winget install failed. Trying Chocolatey ...
    choco install ffmpeg -y >nul 2>&1
    if errorlevel 1 (
        echo   [X] Auto-install failed. Please install FFmpeg manually:
        echo        winget install FFmpeg
        echo        or download from https://ffmpeg.org/download.html
        echo(
        echo   After installing, restart this script.
        pause
        exit /b 1
    )
)

:: refresh PATH to pick up new install
for /f %%i in ('where ffmpeg 2^>nul') do (
    set "FFMPEG_PATH=%%~dpi"
    set "PATH=%%~dpi;%PATH%"
    goto :ffmpeg_ready
)

:: still not found -- try common paths
for %%p in ("%ProgramFiles%\FFmpeg\bin\ffmpeg.exe" "%ProgramFiles(x86)%\FFmpeg\bin\ffmpeg.exe" "%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe" "C:\tools\ffmpeg\bin\ffmpeg.exe") do (
    if exist "%%~p" (
        set "PATH=%%~dp;%PATH%"
        goto :ffmpeg_ready
    )
)

echo   [X] FFmpeg installed but not found in expected locations.
echo   Please restart this script after installing FFmpeg.
pause
exit /b 1

:ffmpeg_ready
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   [X] FFmpeg binary is present but not working -- please reinstall
    pause
    exit /b 1
)
echo   [V] FFmpeg ready
echo(

:: 7. check ffprobe
echo   [*] Checking ffprobe ...
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo   [!] ffprobe not found -- some audio analysis may fail
) else (
    echo   [V] ffprobe ready
)
echo(

:: summary
echo ================================================================
echo   All checks passed -- launching services
echo ================================================================
echo(

:: launch
echo ================================================================
echo   Launching services
echo ================================================================
echo(

echo   [*] Starting backend (uvicorn) ...
start "Trimora Backend" /D "%ROOT%" "%VENV_DIR%\Scripts\python.exe" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
echo   [V] Backend starting at http://localhost:8000
timeout /t 2 /nobreak >nul

echo   [*] Starting frontend (Vite) ...
start "Trimora Frontend" /D "%FRONTEND_DIR%" cmd /k "npx vite --host 0.0.0.0 --port 5173"
echo   [V] Frontend starting at http://localhost:5173
echo(

echo   [V] Trimora is running
echo   [*] Backend  -- http://localhost:8000
echo   [*] Frontend -- http://localhost:5173
echo(
echo   Close this window or press Ctrl+C to stop
echo(

pause
exit /b 0
