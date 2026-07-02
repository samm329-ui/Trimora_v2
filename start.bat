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
call :log ok   "Node.js found"
echo(

:: ──────────────────────────────────────
:: 3. check / set up venv
:: ──────────────────────────────────────
call :log info "Setting up Python virtual environment …"
if not exist "%VENV_DIR%\Scripts\python.exe" (
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

call :log info "Installing backend dependencies …"
"%VENV_DIR%\Scripts\pip" install -q -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    call :log fail "pip install failed — check requirements.txt"
    pause
    exit /b 1
)
call :log ok   "Backend dependencies installed"
echo(

:: ──────────────────────────────────────
:: 4. check / install frontend deps
:: ──────────────────────────────────────
call :log info "Checking frontend dependencies …"
if not exist "%FRONTEND_DIR%\node_modules" (
    call :log info "Installing frontend dependencies (npm ci) …"
    cd /d "%FRONTEND_DIR%"
    call npm ci
    if errorlevel 1 (
        call :log warn "npm ci failed — falling back to npm install"
        call npm install
        if errorlevel 1 (
            call :log fail "npm install failed"
            pause
            exit /b 1
        )
    )
    cd /d "%ROOT%"
    call :log ok   "Frontend dependencies installed"
) else (
    call :log ok   "Frontend dependencies ready")
echo(

:: ──────────────────────────────────────
:: 5. check FFmpeg  (critical)
:: ──────────────────────────────────────
call :log info "Checking FFmpeg …"
set "FFMPEG_PATH="
where ffmpeg >nul 2>&1
if errorlevel 1 (
    call :log warn "FFmpeg not in PATH — searching common locations …"

    set "CANDIDATES=%ProgramFiles%\FFmpeg\bin;%ProgramFiles(x86)%\FFmpeg\bin;%LocalAppData%\Microsoft\WinGet\Packages\FFmpeg;%USERPROFILE%\scoop\apps\ffmpeg\current\bin;C:\tools\ffmpeg\bin"
    for %%p in ("%ProgramFiles%\FFmpeg\bin\ffmpeg.exe"
                "%ProgramFiles(x86)%\FFmpeg\bin\ffmpeg.exe"
                "%LocalAppData%\Microsoft\WinGet\Packages\FFmpeg\*ffmpeg.exe"
                "%USERPROFILE%\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
                "C:\tools\ffmpeg\bin\ffmpeg.exe") do (
        if exist "%%~p" (
            set "FFMPEG_PATH=%%~dp"
            goto :ffmpeg_found
        )
    )

    call :log fail "FFmpeg not found — install it (scoop install ffmpeg or winget install FFmpeg) and restart"
    pause
    exit /b 1

    :ffmpeg_found
    call :log ok   "FFmpeg found at !FFMPEG_PATH!"
) else (
    for /f "delims=" %%i in ('where ffmpeg') do set "FFMPEG_BIN=%%~dpi"
    set "FFMPEG_PATH=!FFMPEG_BIN!"
    call :log ok   "FFmpeg found in PATH"
)

set "PATH=%FFMPEG_PATH%;%PATH%"

:: verify ffmpeg actually works
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    call :log fail "FFmpeg binary is not working — reinstall FFmpeg"
    pause
    exit /b 1
)
call :log ok   "FFmpeg ready"
echo(

:: ──────────────────────────────────────
:: summary
:: ──────────────────────────────────────
echo ┌──────────────────────────────────────────────────────┐
echo │  %BOLD%%CYAN%All checks passed — ready to launch%RESET%           │
echo └──────────────────────────────────────────────────────┘
echo(

:: ──────────────────────────────────────
:: launch
:: ──────────────────────────────────────
call :log step "Launching services"
echo(
call :log info "Starting backend …"
start "Trimora Backend" cmd /c "%VENV_DIR%\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000" 2>&1
if errorlevel 1 (
    call :log fail "Backend failed to start"
    pause
    exit /b 1
)
call :log ok   "Backend running on http://localhost:8000"

call :log info "Starting frontend …"
start "Trimora Frontend" cmd /c "cd /d "%FRONTEND_DIR%" && npx vite --host 0.0.0.0 --port 5173"
call :log ok   "Frontend running on http://localhost:5173"
echo(

call :log info "Backend  — http://localhost:8000"
call :log info "Frontend — http://localhost:5173"
echo(
call :log step "Close this window to stop both services"
echo(

pause
exit /b 0


:: ──────────────────────────────────────
:: helpers
:: ──────────────────────────────────────
:log
if "%~1"=="step" (
    echo %BOLD%%CYAN%[•••] %~2%RESET%
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
