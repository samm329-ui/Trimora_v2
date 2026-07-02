@echo off
setlocal enabledelayedexpansion

title Trimora — Launcher

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

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
python --version
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
    call :log info "Creating virtual environment at %VENV_DIR% …"
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        call :log fail "Failed to create virtual environment"
        pause
        exit /b 1
    )
    call :log ok   "Virtual environment created"
) else (
    call :log ok   "Virtual environment exists"
)
echo(

:: ──────────────────────────────────────
:: 4. pip install
:: ──────────────────────────────────────
call :log step "Installing backend Python packages"
echo(
call :log info "Running: pip install -r requirements.txt"
echo(
"%VENV_DIR%\Scripts\pip" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    call :log fail "pip install failed — check requirements.txt and your internet connection"
    pause
    exit /b 1
)
echo(
call :log ok   "Backend dependencies installed"
echo(

:: ──────────────────────────────────────
:: 5. frontend npm install
:: ──────────────────────────────────────
call :log step "Installing frontend packages"
echo(
if not exist "%FRONTEND_DIR%\node_modules" (
    call :log info "Running: npm install in frontend/"
    echo(
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        popd
        call :log fail "npm install failed — check your internet connection and package.json"
        pause
        exit /b 1
    )
    popd
    call :log ok   "Frontend dependencies installed"
) else (
    call :log ok   "node_modules already exists — skipping"
)
echo(

:: ──────────────────────────────────────
:: 6. check FFmpeg
:: ──────────────────────────────────────
call :log step "Checking FFmpeg"
echo(
set "FFMPEG_OK=no"
where ffmpeg >nul 2>&1
if not errorlevel 1 set "FFMPEG_OK=yes"

if not "!FFMPEG_OK!"=="yes" (
    call :log warn "FFmpeg not in PATH — scanning common install locations …"
    for %%p in ("%ProgramFiles%\FFmpeg\bin\ffmpeg.exe" "%ProgramFiles(x86)%\FFmpeg\bin\ffmpeg.exe" "%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe" "C:\tools\ffmpeg\bin\ffmpeg.exe" "%USERPROFILE%\AppData\Local\ffmpeg\bin\ffmpeg.exe") do (
        if exist "%%~p" (
            set "FFMPEG_OK=yes"
            set "PATH=%%~dp;%PATH%"
            call :log ok "Found at %%~p"
        )
    )
)

if not "!FFMPEG_OK!"=="yes" (
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
)

ffmpeg -version >nul 2>&1
if errorlevel 1 (
    call :log fail "FFmpeg binary is present but not working — reinstall"
    pause
    exit /b 1
)
call :log ok   "FFmpeg ready"
echo(

:: ──────────────────────────────────────
:: 7. check ffprobe
:: ──────────────────────────────────────
call :log info "Checking ffprobe …"
where ffprobe >nul 2>&1
if errorlevel 1 (
    call :log warn "ffprobe not found — some audio analysis may fail"
) else (
    call :log ok "ffprobe ready"
)
echo(

:: ──────────────────────────────────────
:: summary
:: ──────────────────────────────────────
echo ================================================================
echo   All checks passed — launching services
echo ================================================================
echo(
call :log info "Backend  → http://localhost:8000"
call :log info "Frontend → http://localhost:5173"
echo(

:: ──────────────────────────────────────
:: launch
:: ──────────────────────────────────────
call :log step "Launching services"
echo(

call :log info "Starting backend (uvicorn) …"
start "Trimora Backend" /D "%ROOT%" "%VENV_DIR%\Scripts\python.exe" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
if errorlevel 1 (
    call :log fail "Failed to launch backend"
    pause
    exit /b 1
)
call :log ok   "Backend starting at http://localhost:8000"
timeout /t 2 /nobreak >nul

call :log info "Starting frontend (Vite) …"
start "Trimora Frontend" /D "%FRONTEND_DIR%" cmd /k "npx vite --host 0.0.0.0 --port 5173"
call :log ok   "Frontend starting at http://localhost:5173"
echo(

call :log ok "Services started — Trimora is running"
call :log info "Backend  → http://localhost:8000"
call :log info "Frontend → http://localhost:5173"
echo(
pause
exit /b 0


:: ──────────────────────────────────────
:: helper — simple echo wrapper
:: ──────────────────────────────────────
:log
echo   %~2
exit /b 0
