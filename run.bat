@echo off
rem Start / stop the Trajectory Analyzer Streamlit app on Windows.
rem
rem Usage (cmd):
rem   run.bat start     - launch the app in the background
rem   run.bat stop      - stop the running app
rem   run.bat restart   - stop then start
rem   run.bat status    - show whether it's running
rem
rem Override the port with:  set PORT=1234 && run.bat start

setlocal enabledelayedexpansion
cd /d "%~dp0"

if "%PORT%"=="" set "PORT=8501"
set "LOGFILE=streamlit.log"
set "TITLE=Trajectory Analyzer"

set "ACTION=%~1"
if /i "%ACTION%"=="start"   goto start
if /i "%ACTION%"=="stop"    goto stop
if /i "%ACTION%"=="restart" goto restart
if /i "%ACTION%"=="status"  goto status
goto usage

:start
call :isrunning
if "!RUNNING!"=="1" (
    echo Already running on port %PORT%.
    goto :eof
)
echo Starting Trajectory Analyzer on http://localhost:%PORT% ...
start "%TITLE%" /min cmd /c "streamlit run app.py --server.headless true --server.port %PORT% > %LOGFILE% 2>&1"
set /a tries=0
:waitloop
set /a tries+=1
if exist "%LOGFILE%" (
    findstr /c:"You can now view" "%LOGFILE%" >nul 2>&1 && (
        echo Started. Logs: %LOGFILE%
        goto :eof
    )
)
if !tries! geq 40 (
    echo Started, but readiness not confirmed. Check %LOGFILE%.
    goto :eof
)
timeout /t 1 /nobreak >nul
goto waitloop

:stop
call :isrunning
if not "!RUNNING!"=="1" (
    echo Not running.
    goto :eof
)
echo Stopping ...
taskkill /FI "WINDOWTITLE eq %TITLE%*" /T /F >nul 2>&1
echo Stopped.
goto :eof

:restart
call :stop
call :start
goto :eof

:status
call :isrunning
if "!RUNNING!"=="1" (
    echo Running on port %PORT%.
) else (
    echo Not running.
)
goto :eof

:isrunning
set "RUNNING=0"
tasklist /FI "WINDOWTITLE eq %TITLE%*" 2>nul | findstr /i "cmd.exe" >nul 2>&1 && set "RUNNING=1"
goto :eof

:usage
echo Usage: run.bat {start^|stop^|restart^|status}
exit /b 1
