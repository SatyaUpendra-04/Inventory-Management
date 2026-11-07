@echo off
rem Launches the app from the project's virtual environment.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m ims
