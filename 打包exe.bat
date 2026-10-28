@echo off
rem Build dist\桌面表情Ping.exe with PyInstaller.
cd /d "%~dp0"
chcp 65001 >nul
where python >nul 2>nul
if errorlevel 1 (
    echo python.exe not found. Please install Python from python.org and add it to PATH.
    pause
    exit /b 1
)
python build_exe.py
echo.
echo Done. Press any key to close.
pause >nul
