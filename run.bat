@echo off
rem Launches Inventory Management from the project's virtual environment.
rem If the environment is missing or broken, it is rebuilt with uv first.
setlocal
cd /d "%~dp0"

".venv\Scripts\python.exe" -c "import ims, PySide6" >nul 2>&1
if not errorlevel 1 goto launch

echo The app environment is missing or broken. Rebuilding it, please wait...
call :find_uv
if not defined UV (
    echo.
    echo uv was not found. Install it from https://docs.astral.sh/uv/ and run this again.
    pause
    exit /b 1
)
%UV% sync
".venv\Scripts\python.exe" -c "import ims, PySide6" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Could not prepare the app environment.
    echo See "Development setup" in README.md, or send the messages above to support.
    pause
    exit /b 1
)

:launch
start "" ".venv\Scripts\pythonw.exe" -m ims
exit /b 0

:find_uv
rem 1) uv on PATH  2) uv installed for this user with pip  3) uv as a module of Python 3.14
set "UV="
where uv >nul 2>&1 && set "UV=uv" && exit /b 0
for /d %%D in ("%APPDATA%\Python\Python3*") do (
    if exist "%%D\Scripts\uv.exe" set "UV="%%D\Scripts\uv.exe"" && exit /b 0
)
py -3.14 -m uv --version >nul 2>&1 && set "UV=py -3.14 -m uv"
exit /b 0
