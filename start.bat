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

echo   [*] FFmpeg not found. Attempting auto-install ...
echo(
where winget >nul 2>&1
if errorlevel 1 (
    echo   [!] winget not available on this system -- skipping
    goto :try_choco
)
echo   Press any key to install FFmpeg via winget.
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

:try_choco
if not defined FFMPEG_FOUND (
    where choco >nul 2>&1
    if errorlevel 1 (
        echo   [!] Chocolatey not available either
        goto :manual_install
    )
    echo   [*] Installing FFmpeg via Chocolatey ...
    echo(
    choco install ffmpeg -y
    echo(
    call :find_ffmpeg
)

:manual_install
if not defined FFMPEG_FOUND (
    echo   [X] Could not install via winget or Chocolatey.
    echo(
    echo   Press any key to download FFmpeg directly (no admin needed).
    echo   Will install to: %LOCALAPPDATA%\ffmpeg
    echo(
    pause

    echo   [*] Downloading FFmpeg from gyan.dev ...
    set "FFMPEG_ZIP=%TEMP%\ffmpeg-release.zip"
    set "FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

    powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%FFMPEG_ZIP%' -UseBasicParsing; exit 0 } catch { Write-Host 'Download failed'; exit 1 }"
    if errorlevel 1 (
        echo   [X] Download failed. Check your internet connection.
        echo   Please download manually from https://ffmpeg.org/download.html
        pause
        exit /b 1
    )

    echo   [*] Extracting FFmpeg ...
    if exist "%LOCALAPPDATA%\ffmpeg" rmdir /s /q "%LOCALAPPDATA%\ffmpeg"
    powershell -Command "try { Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory('%FFMPEG_ZIP%', '%LOCALAPPDATA%\ffmpeg'); exit 0 } catch { Write-Host 'Extract failed'; exit 1 }"
    del "%FFMPEG_ZIP%" >nul 2>&1

    :: Find the extracted ffmpeg.exe (it's in a versioned subfolder like ffmpeg-7.1-full_build)
    set "FFMPEG_FOUND="
    for /d %%d in ("%LOCALAPPDATA%\ffmpeg\ffmpeg-*") do (
        if exist "%%d\bin\ffmpeg.exe" (
            set "FFMPEG_FOUND=1"
            set "FFMPEG_INSTALL_DIR=%%d\bin"
            set "PATH=%%d\bin;%PATH%"
        )
    )

    if not defined FFMPEG_FOUND (
        :: Maybe extracted directly
        if exist "%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe" (
            set "FFMPEG_FOUND=1"
            set "FFMPEG_INSTALL_DIR=%LOCALAPPDATA%\ffmpeg\bin"
            set "PATH=%LOCALAPPDATA%\ffmpeg\bin;%PATH%"
        )
    )

    if not defined FFMPEG_FOUND (
        echo   [X] Downloaded but couldn't find ffmpeg.exe in the extracted files.
        echo   Please install manually from https://ffmpeg.org/download.html
        pause
        exit /b 1
    )

    echo   [V] FFmpeg installed to !FFMPEG_INSTALL_DIR!
    echo(
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
