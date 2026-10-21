@echo off
rem Double-click to start ClassMate on Windows. The first run installs everything (a few minutes).
rem API keys are entered in the app (settings panel opens by itself when a key is missing).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: installing ClassMate, this takes a few minutes...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>nul
    if errorlevel 1 (
      echo Python 3 was not found. Install it from https://www.python.org/downloads/windows/
      echo and tick "Add python.exe to PATH" during setup, then double-click this file again.
      pause
      exit /b 1
    )
    python -m venv .venv
  )
  if not exist ".venv\Scripts\python.exe" (
    echo Could not create the virtual environment.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
)

rem (re)install when pyproject.toml is newer than the last install
".venv\Scripts\python.exe" -c "import os,sys;m='.venv/.installed';sys.exit(0 if os.path.exists(m) and os.path.getmtime(m)>=os.path.getmtime('pyproject.toml') else 1)"
if errorlevel 1 (
  echo Installing / updating dependencies...
  ".venv\Scripts\python.exe" -m pip install -q -e .
  if errorlevel 1 (
    echo Installation failed. Please send the error above to the author.
    pause
    exit /b 1
  )
  type nul > ".venv\.installed"
)

echo Slides: put PDF / PPT files into the notes folder and they are loaded automatically.
".venv\Scripts\python.exe" -m classmate %*
if errorlevel 1 pause
