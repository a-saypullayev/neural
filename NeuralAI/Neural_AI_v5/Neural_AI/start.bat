@echo off
title Neural Search Chatbot
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (echo Python was not found. Install Python 3.11+ and enable Add to PATH.& pause & exit /b 1)
where ollama >nul 2>nul
if errorlevel 1 (echo Ollama was not found. Install and open Ollama first.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (echo Creating Python environment...& py -m venv .venv)
echo Installing requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Package installation failed.& pause & exit /b 1)
echo.
".venv\Scripts\python.exe" scripts\init_env.py
echo Make sure qwen3.5:4b is installed. Run: ollama pull qwen3.5:4b
echo Starting Neural. Open http://127.0.0.1:8000
set "AI_BASE_URL=http://127.0.0.1:11434/v1"
set "AI_API_KEY=ollama"
set "AI_MODEL=qwen3.5:4b"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
