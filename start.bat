@echo off
REM Funnel - Start n8n with environment variables
REM Run from the jobs_funnel directory

echo Starting Funnel (n8n) at http://localhost:5678
echo.
echo Press Ctrl+C to stop
echo.

npx dotenv -e .env -- n8n start
