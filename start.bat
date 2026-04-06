@echo off
REM Jobs funnel - Start Postgres + n8n with environment variables
REM Run from the jobs_funnel directory

echo Starting Postgres container...
docker compose up -d
echo Waiting for Postgres to be ready...
timeout /t 3 /nobreak >nul
echo.
echo Starting Jobs funnel (n8n) at http://localhost:5678
echo.
echo Press Ctrl+C to stop
echo.

set NODE_FUNCTION_ALLOW_BUILTIN=fs,path,os
set N8N_RUNNERS_TASK_TIMEOUT=600
npx dotenv -e .env -- n8n start
