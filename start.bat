@echo off
REM Jobs funnel - transparent local startup helper
REM Run from the jobs_funnel directory

if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment not found. Run: python -m venv .venv
  exit /b 1
)
if not exist "node_modules\.bin\n8n.cmd" (
  echo Project n8n installation not found. Run: npm ci
  exit /b 1
)
set "PATH=%CD%\.venv\Scripts;%PATH%"

echo Starting Postgres container...
docker compose up -d
if %ERRORLEVEL% neq 0 (
  echo Docker startup failed.
  exit /b %ERRORLEVEL%
)
echo.
echo Running quick setup checks...
.venv\Scripts\python.exe scripts\doctor.py --prestart
if %ERRORLEVEL% neq 0 (
  echo Doctor checks failed.
  exit /b %ERRORLEVEL%
)
echo.
echo Starting n8n at http://localhost:5678
echo Jobs Funnel UI runs separately:
echo   .venv\Scripts\python.exe -m uvicorn ui.server:app --host 127.0.0.1 --port 8080
echo Then open http://localhost:8080
echo.
echo Press Ctrl+C to stop n8n
echo.

set NODE_FUNCTION_ALLOW_BUILTIN=fs,path,os
set N8N_RUNNERS_TASK_TIMEOUT=600
npm.cmd run n8n:start
