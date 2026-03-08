@echo off
REM Start 3 Celery workers for parallel task execution
REM Each worker has a unique name to avoid conflicts

echo Starting 3 Celery workers...
echo.

REM Activate venv first
call venv\Scripts\activate.bat

for /L %%i in (1,1,3) do (
    start "Worker %%i" cmd /k "venv\Scripts\activate.bat && celery -A config worker --loglevel=info -n worker%%i@%%COMPUTERNAME%%"
    timeout /t 2 /nobreak
)

echo.
echo 3 workers launched! Check the windows above.
echo Press any key to close this window...
pause
