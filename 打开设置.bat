@echo off
rem Open the settings window. If the tool is already running, this asks that
rem instance to show its settings instead of starting a second copy.
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
    echo pythonw.exe not found. Please install Python from python.org and add it to PATH.
    pause
    exit /b 1
)
start "" pythonw "%~dp0main.py" --settings
exit /b 0
