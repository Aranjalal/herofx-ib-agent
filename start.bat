@echo off
REM HeroFX IB Agent - Quick Start
echo Starting HeroFX IB Agent...

REM Check for Gemini API key
if "%GEMINI_API_KEY%"=="" (
    echo ERROR: GEMINI_API_KEY is not set!
    echo Set it with: set GEMINI_API_KEY=your_key
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate

REM Run the agent
python main.py

pause
