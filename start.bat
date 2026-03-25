@echo off
REM Funnel - Start n8n with environment variables
REM Run from the jobs_funnel directory

echo Starting Funnel (n8n) at http://localhost:5678
echo.
echo Press Ctrl+C to stop
echo.

set NODE_FUNCTION_ALLOW_BUILTIN=fs,path,os
set N8N_RUNNERS_TASK_TIMEOUT=600
npx dotenv -e .env -- n8n start
