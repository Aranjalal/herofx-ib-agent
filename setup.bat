@echo off
REM HeroFX IB Agent - Windows Setup Script
echo =========================================
echo   HeroFX IB Agent - Windows Setup
echo =========================================

echo.
echo [1/4] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed! Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)
echo Python found!

echo.
echo [2/4] Creating virtual environment...
python -m venv venv
echo Virtual environment created!

echo.
echo [3/4] Installing dependencies...
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
echo Dependencies installed!

echo.
echo [4/4] Installing Playwright browsers...
playwright install chromium
echo Playwright installed!

echo.
echo =========================================
echo   Setup Complete!
echo =========================================
echo.
echo Next steps:
echo 1. Get Gemini API key from https://aistudio.google.com/apikey
echo 2. Set environment variable: set GEMINI_API_KEY=your_key
echo 3. Update config.json with your Telegram bot tokens
echo 4. Run: python main.py
echo.
pause
