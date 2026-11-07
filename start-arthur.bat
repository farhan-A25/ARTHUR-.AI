@echo off
REM ============================================================
REM  ARTHUR — Full App Launcher (Windows)
REM  Owner: Mohammed Farhan
REM  Reads arthur.config.json (single shared config) and starts:
REM    API server + dashboard AND the CLI with 24/7 worker.
REM  It also auto-writes mobile\.env so the phone app talks to
REM  this same backend — everything combined, nothing to wire.
REM  Usage: double-click start-arthur.bat
REM ============================================================
cd /d "%~dp0"

for /f "delims=" %%A in ('python -c "import json;print(json.load(open('arthur.config.json')).get('api_url','http://localhost:8000'))"') do set API_URL=%%A
for /f "delims=" %%A in ('python -c "import json;print(json.load(open('arthur.config.json')).get('api_host','127.0.0.1'))"') do set API_HOST=%%A
for /f "delims=" %%A in ('python -c "import json;print(json.load(open('arthur.config.json')).get('api_port',8000))"') do set API_PORT=%%A
for /f "delims=" %%A in ('python -c "import json;print(str(json.load(open('arthur.config.json')).get('demo_mode',True)).lower())"') do set DEMO_MODE_CFG=%%A

if not exist .venv (
  echo ^>^> First run: creating virtual environment...
  python -m venv .venv
)

echo ^>^> Installing requirements...
.venv\Scripts\pip install -q -r requirements.txt

REM Combine: point the mobile app at this backend automatically.
> mobile\.env echo EXPO_PUBLIC_ARTHUR_API_URL=%API_URL%
echo ^>^> Mobile app wired to backend: %API_URL%

if "%DEMO_MODE%"=="" set DEMO_MODE=%DEMO_MODE_CFG%

echo ^>^> Starting ARTHUR API + dashboard at %API_URL% ...
start "ARTHUR API" .venv\Scripts\python -m uvicorn backend.api.server:app --host %API_HOST% --port %API_PORT%

echo ^>^> Dashboard: %API_URL%
echo ^>^> Starting ARTHUR console (worker included). Type /quit to stop everything.
echo.
.venv\Scripts\python backend/main.py
