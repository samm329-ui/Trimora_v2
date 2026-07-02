@echo off
setlocal enabledelayedexpansion

title Trimora — Launcher

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

:: ──────────────────────────────────────
:: colour helpers
:: ──────────────────────────────────────
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "CYAN=[96m"
set "BOLD=[1m"
set "RESET=[0m"

call :log step "Trimora — pre-flight checks"
echo(

:: ──────────────────────────────────────
:: 1. check Python
:: ──────────────────────────────────────
call :log info "Checking Python …"
where python >nul 2>&1
if errorlevel 1 (
    call :log fail "Python not found — install Python 3.10+ and try again"
    pause
    exit /b 1
)
python --version 2>&1 | findstr /R "3\.\(1[0-9]\|[0-9]\)" >nul
if errorlevel 1 (
    call :log warn "Python 3.10+ recommended — you have:"
    python --version
)
call :log ok   "Python found"
echo(

:: ──────────────────────────────────────
:: 2. check Node.js
:: ──────────────────────────────────────
call :log info "Checking Node.js …"
where node >nul 2>&1
if errorlevel 1 (
    call :log fail "Node.js not found — install Node.js 18+ and try again"
    pause
    exit /b 1
)
node --version
call :log ok   "Node.js found"
echo(

:: ──────────────────────────────────────
:: 3. check / set up venv
:: ──────────────────────────────────────
call :log info "Setting up Python virtual environment …"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   %CYAN%[*]%RESET% Creating virtual environment at %VENV_DIR% …
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        call :log fail "Failed to create virtual environment"
        pause
        exit /b 1
    )
    call :log ok   "Virtual environment created"
) else (
    call :log ok   "Virtual environment exists at %VENV_DIR%"
)
echo(

:: ──────────────────────────────────────
:: 3b. pip install (verbose — shows packages, sizes, progress)
:: ──────────────────────────────────────
call :log step "Installing backend Python packages"
echo(
echo   This installs: FastAPI, uvicorn, numpy, sentence-transformers, PyYAML, pytest, httpx, and more
echo   Location: %VENV_DIR%
echo(
"%VENV_DIR%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    call :log fail "pip install failed — check requirements.txt and your internet connection"
    pause
    exit /b 1
)
echo(
call :log ok   "All backend Python packages installed"
call :log info "Packages installed:"
"%VENV_DIR%\Scripts\pip" list --format=columns 2>nul
echo(

:: ──────────────────────────────────────
:: 4. frontend npm install (verbose)
:: ──────────────────────────────────────
call :log step "Installing frontend packages (npm)"
echo(
echo   Packages: react, react-dom, vite, typescript, tailwindcss, and more
echo   Location: %FRONTEND_DIR%\node_modules
echo(
if not exist "%FRONTEND_DIR%\node_modules" (
    cd /d "%FRONTEND_DIR%"
    echo   %CYAN%[*]%RESET% Running npm install — this may take 1-3 minutes depending on your internet speed
    echo   %CYAN%[*]%RESET% npm will show package name, progress bar, and estimated time for each phase
    echo(
    call npm install
    if errorlevel 1 (
        call :log fail "npm install failed — check your internet connection and package.json"
        pause
        exit /b 1
    )
    echo(
    call :log ok   "All frontend packages installed"
    call :log info "Installed packages:"
    call npm list --depth=0 2>nul
    echo(
    cd /d "%ROOT%"
) else (
    call :log ok   "node_modules already exists — skipping install"
    call :log info "Run 'npm update' inside frontend/ to refresh packages"
)
echo(

:: ──────────────────────────────────────
:: 5. check FFmpeg  (critical)
:: ──────────────────────────────────────
call :log step "Checking FFmpeg (required for audio/video processing)"
echo(
set "FFMPEG_PATH="
where ffmpeg >nul 2>&1
if errorlevel 1 (
    call :log warn "FFmpeg not in PATH — searching common locations …"
    echo(

    for %%p in ("%ProgramFiles%\FFmpeg\bin\ffmpeg.exe"
                "%ProgramFiles(x86)%\FFmpeg\bin\ffmpeg.exe"
                "%LocalAppData%\Microsoft\WinGet\Packages\FFmpeg\*ffmpeg.exe"
                "%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
                "C:\tools\ffmpeg\bin\ffmpeg.exe"
                "%USERPROFILE%\AppData\Local\ffmpeg\bin\ffmpeg.exe") do (
        if exist "%%~p" (
            set "FFMPEG_PATH=%%~dp"
            echo   %GREEN%[✓]%RESET% Found at %%~p
            goto :ffmpeg_found
        )
    )

    call :log fail "FFmpeg not found — install it and try again"
    echo(
    echo   Install options:
    echo     winget install FFmpeg
    echo     scoop install ffmpeg
    echo     choco install ffmpeg
    echo     or download from https://ffmpeg.org/download.html
    echo(
    pause
    exit /b 1

    :ffmpeg_found
) else (
    for /f "delims=" %%i in ('where ffmpeg') do set "FFMPEG_BIN=%%~dpi"
    set "FFMPEG_PATH=!FFMPEG_BIN!"
    call :log ok   "FFmpeg found in PATH at !FFMPEG_PATH!"
)

set "PATH=%FFMPEG_PATH%;%PATH%"

:: verify ffmpeg actually works
echo   %CYAN%[*]%RESET% Verifying FFmpeg binary …
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    call :log fail "FFmpeg binary is present but not working — reinstall FFmpeg"
    pause
    exit /b 1
)
for /f "tokens=1-3" %%a in ('ffmpeg -version 2^>^&1 ^| findstr "ffmpeg version"') do set "FFMPEG_VER=%%b"
echo   %GREEN%[✓]%RESET% FFmpeg ready — version %FFMPEG_VER%
echo(

:: ──────────────────────────────────────
:: 6. check ffprobe (comes with FFmpeg)
:: ──────────────────────────────────────
call :log info "Checking ffprobe …"
where ffprobe >nul 2>&1
if errorlevel 1 (
    call :log warn "ffprobe not found — some audio analysis may fail"
) else (
    call :log ok   "ffprobe ready"
)
echo(

:: ──────────────────────────────────────
:: summary
:: ──────────────────────────────────────
echo ┌──────────────────────────────────────────────────────────────────┐
echo │  %BOLD%%GREEN%  All checks passed — launching services%RESET%                     │
echo └──────────────────────────────────────────────────────────────────┘
echo(
echo   %CYAN%Python%RESET%      %BOLD%%VENV_DIR%\Scripts\python.exe%RESET%
echo   %CYAN%Backend%RESET%     http://localhost:8000
echo   %CYAN%Frontend%RESET%    http://localhost:5173
echo   %CYAN%FFmpeg%RESET%      %FFMPEG_PATH%
echo(

:: ──────────────────────────────────────
:: launch
:: ──────────────────────────────────────
call :log step "Launching services"
echo(

call :log info "Starting backend (uvicorn) …"
echo   %CYAN%[*]%RESET% Command: %VENV_DIR%\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
start "Trimora Backend" cmd /k "%VENV_DIR%\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 && title Trimora Backend"
timeout /t 2 /nobreak >nul
call :log ok   "Backend starting at http://localhost:8000"

call :log info "Starting frontend (Vite) …"
echo   %CYAN%[*]%RESET% Command: npx vite --host 0.0.0.0 --port 5173
start "Trimora Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npx vite --host 0.0.0.0 --port 5173 && title Trimora Frontend"
call :log ok   "Frontend starting at http://localhost:5173"
echo(

echo   %BOLD%%GREEN%[✓] Trimora is running%RESET%
echo   %BOLD%%CYAN%    Backend  → http://localhost:8000%RESET%
echo   %BOLD%%CYAN%    Frontend → http://localhost:5173%RESET%
echo(
echo   %YELLOW%Close this window or press Ctrl+C to stop all services%RESET%
echo(

pause
exit /b 0


:: ──────────────────────────────────────
:: helpers
:: ──────────────────────────────────────
:log
if "%~1"=="step" (
    echo ═══════════════════════════════════════════════════════════════════
    echo   %BOLD%%CYAN%%~2%RESET%
    echo ═══════════════════════════════════════════════════════════════════
    exit /b 0
)
if "%~1"=="info" (
    echo   %CYAN%[*]%RESET% %~2
    exit /b 0
)
if "%~1"=="ok" (
    echo   %GREEN%[✓]%RESET% %~2
    exit /b 0
)
if "%~1"=="warn" (
    echo   %YELLOW%[!]%RESET% %~2
    exit /b 0
)
if "%~1"=="fail" (
    echo   %RED%[✗]%RESET% %~2
    exit /b 0
)
exit /b 0
