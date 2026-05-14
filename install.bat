@echo off
setlocal EnableDelayedExpansion

echo ==========================================
echo   GNUTempo Windows Installer
echo ==========================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [OK] Python found.
python -c "import sys; print('Version:', sys.version)"

:: 2. Install dependencies (pygame)
echo.
echo Installing dependencies (pygame)...
pip install pygame
if %errorlevel% neq 0 (
    echo [WARNING] Failed to install pygame automatically.
    echo Please run: pip install pygame
) else (
    echo [OK] Dependencies installed.
)

:: 3. Create the 'gnutempo' command wrapper
echo.
echo Creating system command...
set "SCRIPT_DIR=%~dp0"
set "WRAPPER_FILE=%SCRIPT_DIR%gnutempo.cmd"

(
    echo @echo off
    echo python "%SCRIPT_DIR%OpenTempo.py" %%*
) > "!WRAPPER_FILE!"

echo [OK] Created wrapper script: gnutempo.cmd

:: 4. Instructions for PATH
echo.
echo ==========================================
echo   INSTALLATION COMPLETE
echo ==========================================
echo.
echo To run 'gnutempo' from any terminal, you need to add this folder to your PATH.
echo.
echo Current Folder: %SCRIPT_DIR%
echo.
echo OPTION A (Easy): Run this script from this folder always.
echo   Usage: .\gnutempo start
echo.
echo OPTION B (System-wide): Add this folder to your Environment Variables.
echo   1. Press Win+R, type 'sysdm.cpl', hit Enter.
echo   2. Go to 'Advanced' tab -^> 'Environment Variables'.
echo   3. Under 'User variables', find 'Path', select it, click 'Edit'.
echo   4. Click 'New' and paste: %SCRIPT_DIR%
echo   5. Click OK on all windows.
echo   6. Restart your terminal.
echo.
echo After Option B, you can run 'gnutempo' from anywhere!
echo.
pause
