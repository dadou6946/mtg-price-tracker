@echo off
REM Start Celery Beat scheduler for periodic tasks
REM Requires Redis to be running and at least 1 worker

echo Starting Celery Beat scheduler...
echo.
echo This will schedule tasks to run periodically:
echo   - Every 6 hours: Scrape all tracked cards from all stores
echo.

REM Activate venv first
call venv\Scripts\activate.bat

REM Start Celery Beat (single instance, no -n required)
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

echo.
echo Celery Beat stopped.
pause
