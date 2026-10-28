@echo off
rem Run with console so you can read the log output.
cd /d "%~dp0"
chcp 65001 >nul
python "%~dp0main.py"
echo.
echo Program exited. Press any key to close.
pause >nul
