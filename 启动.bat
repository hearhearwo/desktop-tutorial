@echo off
rem Launch the desktop emoji ping tool without a console window.
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe not found. Please install Python from python.org and add it to PATH.
    pause
    exit /b 1
)
start "" pythonw "%~dp0main.py"
exit /b 0
