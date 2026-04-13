@echo off
title SyncPoint Attendance Server
echo Starting the SyncPoint Backend Server...

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH! Please install Python 3.
    pause
    exit /b
)

:: Create Virtual Environment if it doesn't exist
if not exist venv (
    echo [INFO] Creating Virtual Environment...
    python -m venv venv
)

:: Activate Virtual Environment
echo [INFO] Activating Virtual Environment...
call venv\Scripts\activate.bat

:: Install Requirements
echo [INFO] Installing required Python libraries...
pip install -r requirements.txt

:: Open Browser to Localhost
echo [INFO] Opening Browser to http://localhost:5000 ...
start http://localhost:5000

:: Start Flask App
echo [INFO] Starting Production Server...
python flask_app.py

pause
