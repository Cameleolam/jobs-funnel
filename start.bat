@echo off
REM Funnel - Start n8n with environment variables
REM Run from the jobs_funnel directory

REM Load .env file if it exists
if exist .env (
    for /f "usebackq delims=" %%i in (.env) do (
        REM Skip comments and empty lines
        echo %%i | findstr /r "^#" >nul || (
            echo %%i | findstr /r "^$" >nul || set "%%i"
        )
    )
)

set N8N_BASIC_AUTH_ACTIVE=true
set GENERIC_TIMEZONE=Europe/Berlin

echo Starting Funnel (n8n) at http://localhost:5678
echo.
echo Press Ctrl+C to stop
echo.

n8n start