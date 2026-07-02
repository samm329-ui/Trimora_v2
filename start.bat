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

:: Try to read PATH from registry (sees system-wide changes made by installers)
set "ORIG_PATH=%PATH%"
for /f "skip=2 tokens=3*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do (
    if "%%a"=="REG_SZ" set "SYS_PATH=%%b"
    if "%%a"=="REG_EXPAND_SZ" set "SYS_PATH=%%b"
)
if defined SYS_PATH set "PATH=%SYS_PATH%;%ORIG_PATH%"

:: Search function that scans all known locations and sets PATH if found
set "FFMPEG_FOUND="
call :find_ffmpeg

if defined FFMPEG_FOUND goto :ffmpeg_ready

echo   [*] FFmpeg not found. Attempting auto-install via winget ...
echo(
echo   Press any key to install FFmpeg via winget.
echo   (winget is built into Windows 10/11 -- no download needed)
echo(
pause

winget install "FFmpeg" --accept-source-agreements --accept-package-agreements
echo(

:: After install, refresh PATH from registry again
set "SYS_PATH="
for /f "skip=2 tokens=3*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do (
    if "%%a"=="REG_SZ" set "SYS_PATH=%%b"
    if "%%a"=="REG_EXPAND_SZ" set "SYS_PATH=%%b"
)
if defined SYS_PATH set "PATH=%SYS_PATH%;%ORIG_PATH%"

:: Search again after install
set "FFMPEG_FOUND="
call :find_ffmpeg

if not defined FFMPEG_FOUND (
    echo   [X] Auto-install may have failed. Trying Chocolatey ...
    choco install ffmpeg -y
    echo(
    call :find_ffmpeg
)

if not defined FFMPEG_FOUND (
    echo   [X] Could not locate FFmpeg. Please install manually:
    echo        winget install FFmpeg
    echo        or download from https://ffmpeg.org/download.html
    echo(
    echo   After installing, restart this script.
    pause
    exit /b 1
)

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

:: ─────────────────────────────────────────────────────────
:: :find_ffmpeg  --  search all known locations for ffmpeg.exe
::    Sets FFMPEG_FOUND=1 and prepends the bin dir to PATH
:: ─────────────────────────────────────────────────────────
:find_ffmpeg
where ffmpeg >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%x in ('where ffmpeg') do (
        set "FFMPEG_FOUND=1"
        set "PATH=%%~dpx;%PATH%"
    )
    exit /b 0
)

:: Scan winget packages directory recursively
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages\" (
    for /r "%LOCALAPPDATA%\Microsoft\WinGet\Packages" %%x in (ffmpeg.exe) do (
        if exist "%%x" (
            set "FFMPEG_FOUND=1"
            set "PATH=%%~dpx;%PATH%"
            exit /b 0
        )
    )
)

:: Scan scoop
if exist "%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe" (
    set "FFMPEG_FOUND=1"
    set "PATH=%USERPROFILE%\scoop\apps\ffmpeg\current\bin;%PATH%"
    exit /b 0
)

:: Scan Program Files
if exist "%ProgramFiles%\FFmpeg\bin\ffmpeg.exe" (
    set "FFMPEG_FOUND=1"
    set "PATH=%ProgramFiles%\FFmpeg\bin;%PATH%"
    exit /b 0
)
if exist "%ProgramFiles(x86)%\FFmpeg\bin\ffmpeg.exe" (
    set "FFMPEG_FOUND=1"
    set "PATH=%ProgramFiles(x86)%\FFmpeg\bin;%PATH%"
    exit /b 0
)

:: Scan C:\tools (Chocolatey)
if exist "C:\tools\ffmpeg\bin\ffmpeg.exe" (
    set "FFMPEG_FOUND=1"
    set "PATH=C:\tools\ffmpeg\bin;%PATH%"
    exit /b 0
)

:: Scan local AppData
if exist "%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe" (
    set "FFMPEG_FOUND=1"
    set "PATH=%LOCALAPPDATA%\ffmpeg\bin;%PATH%"
    exit /b 0
)

:: Scan ProgramData (Chocolatey shims)
if exist "%ProgramData%\chocolatey\lib\ffmpeg\tools\ffmpeg.exe" (
    set "FFMPEG_FOUND=1"
    set "PATH=%ProgramData%\chocolatey\lib\ffmpeg\tools;%PATH%"
    exit /b 0
)

exit /b 0
