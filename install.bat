@echo off
REM GNUTempo Windows Installer
REM Installs GNUTempo as a system command on Windows

setlocal enabledelayedexpansion

echo ========================================
echo   GNUTempo Windows Installer
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [OK] Python found
python --version
echo.

REM Check if pygame is installed
python -c "import pygame" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing pygame dependency...
    pip install pygame
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install pygame. Please run: pip install pygame
        pause
        exit /b 1
    )
    echo [OK] pygame installed successfully
) else (
    echo [OK] pygame already installed
)
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Determine installation directory
set "INSTALL_DIR=%USERPROFILE%\gnutempo"
set "BIN_DIR=%USERPROFILE%\AppData\Local\Programs\GNUTempo"

echo [INFO] Installation directory: %INSTALL_DIR%
echo [INFO] Binary directory: %BIN_DIR%
echo.

REM Create installation directories
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo [OK] Created installation directory
)

if not exist "%BIN_DIR%" (
    mkdir "%BIN_DIR%"
    echo [OK] Created binary directory
)

REM Copy main Python script
echo [INFO] Copying OpenTempo.py to installation directory...
copy /Y "%SCRIPT_DIR%\OpenTempo.py" "%INSTALL_DIR%\gnutempo.py" >nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy OpenTempo.py
    pause
    exit /b 1
)
echo [OK] Copied OpenTempo.py

REM Create wrapper batch file
echo [INFO] Creating gnutempo.bat wrapper...
(
echo @echo off
echo REM GNUTempo Wrapper Script
echo set "GNUTEMPO_DIR=%INSTALL_DIR%"
echo python "%%GNUTEMPO_DIR%%\gnutempo.py" %%*
) > "%BIN_DIR%\gnutempo.bat"
echo [OK] Created gnutempo.bat
echo.

REM Add BIN_DIR to PATH (user-level)
echo [INFO] Adding GNUTempo to PATH...
reg query "HKCU\Environment" /v Path >nul 2>&1
if %errorlevel% neq 0 (
    reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "" /f >nul
)

for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CURRENT_PATH=%%B"

echo !CURRENT_PATH! | findstr /C:"%BIN_DIR%" >nul
if %errorlevel% neq 0 (
    if "!CURRENT_PATH!"=="" (
        reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "%BIN_DIR%" /f >nul
    ) else (
        reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "!CURRENT_PATH!;%BIN_DIR%" /f >nul
    )
    echo [OK] Added GNUTempo to PATH
    echo.
    echo [NOTE] You may need to restart your terminal or log out/in for PATH changes to take effect.
) else (
    echo [OK] GNUTempo already in PATH
)
echo.

REM Create uninstaller
echo [INFO] Creating uninstaller...
(
echo @echo off
echo echo Removing GNUTempo installation...
echo.
echo del /Q "%INSTALL_DIR%\gnutempo.py"
echo rmdir "%INSTALL_DIR%" 2^>nul
echo del /Q "%BIN_DIR%\gnutempo.bat"
echo.
echo echo To remove GNUTempo from PATH, manually edit environment variables:
echo echo   - Right-click 'This PC' ^> Properties ^> Advanced system settings
echo echo   - Environment Variables ^> User variables ^> Path
echo echo   - Remove: %BIN_DIR%
echo.
echo echo GNUTempo uninstalled.
echo pause
) > "%BIN_DIR%\uninstall-gnutempo.bat"
echo [OK] Created uninstaller
echo.

REM Test installation
echo [INFO] Testing installation...
call "%BIN_DIR%\gnutempo.bat" --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Installation successful!
) else (
    echo [WARNING] Version check failed, but installation may still work.
)
echo.

echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo Usage:
echo   gnutempo              - Start interactive mode
echo   gnutempo start        - Start metronome
echo   gnutempo --preset jazz - Start with jazz preset
echo   gnutempo --help       - Show all options
echo.
echo Uninstall: Run uninstall-gnutempo.bat from:
echo   %BIN_DIR%
echo.
echo [NOTE] If 'gnutempo' command doesn't work yet, try:
echo   1. Close and reopen your terminal/PowerShell
echo   2. Or use full path: "%BIN_DIR%\gnutempo.bat"
echo.
pause
