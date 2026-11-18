@echo off
setlocal enabledelayedexpansion
title SignBridge — Offline Video Speech-to-Sign Accessibility Server

echo ============================================================
echo   SignBridge — Phase 1 ^& 2 Launcher (Windows)
echo ============================================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.11+ was not found on PATH.
    echo Install Python 3.11 from https://www.python.org/downloads/ and check "Add Python to PATH".
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [WARNING] FFmpeg was not found on PATH.
    echo Audio extraction will fail until FFmpeg is installed and added to PATH.
    echo See README.md for Windows FFmpeg installation steps.
    echo.
)

if not exist "venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"

echo Checking Python dependencies...
python -m pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    pause
    exit /b 1
)

if not exist "models\vosk-model-small-en-us\conf" (
    echo.
    echo [WARNING] Local Vosk model not found at:
    echo   models\vosk-model-small-en-us\
    echo Download vosk-model-small-en-us-0.15.zip from https://alphacephei.com/vosk/models
    echo and extract its contents into models\vosk-model-small-en-us\ before transcribing.
    echo.
)

set PORT=5000
echo Starting SignBridge on http://127.0.0.1:%PORT%
start "" http://127.0.0.1:%PORT%
python app.py

endlocal
