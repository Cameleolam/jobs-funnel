@echo off
REM Jobs funnel - transparent local startup helper
REM Run from the jobs_funnel directory

echo Starting Postgres container...
docker compose up -d
echo.
echo Running quick setup checks...
python scripts\doctor.py
echo.
echo Starting n8n at http://localhost:5678
echo Jobs Funnel UI runs separately:
echo   python -m uvicorn ui.server:app --port 8080 --reload
echo Then open http://localhost:8080
echo.
echo Press Ctrl+C to stop n8n
echo.

set NODE_FUNCTION_ALLOW_BUILTIN=fs,path,os
set N8N_RUNNERS_TASK_TIMEOUT=600
npx dotenv -e .env -- n8n start
