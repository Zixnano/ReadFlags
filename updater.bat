@echo off
setlocal enabledelayedexpansion
rem Usage: updater.bat <host_pid> <staged_package_dir>
rem The staged package folder must contain an "app" folder with the new files.
cd /d "%~dp0"

set "HOST_PID=%~1"
set "STAGED=%~2"

if "%HOST_PID%"=="" goto usage
if "%STAGED%"=="" goto usage

if not exist "%STAGED%\app" (
    echo Staged package has no app folder: %STAGED%
    pause
    exit /b 1
)
if not exist "app" (
    echo Current app folder not found! Nothing to update.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   Read Flags - Post-Exit Updater
echo ==========================================
echo.
echo Waiting for process %HOST_PID% to exit...
set /a WAITED=0

:waitloop
tasklist /FI "PID eq %HOST_PID%" 2>nul | find "%HOST_PID%" >nul
if errorlevel 1 goto swap
set /a WAITED+=1
if !WAITED! GTR 60 (
    echo Timed out waiting for the host process after 60 seconds. Nothing changed.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto waitloop

:swap
if exist app.old rmdir /s /q app.old
if exist app.old (
    echo Could not clear the old backup folder. Check for locked files. Nothing changed.
    pause
    exit /b 1
)

echo Swapping app folder...
ren app app.old
if errorlevel 1 (
    echo The app folder is locked. Update cancelled, nothing changed.
    pause
    exit /b 1
)

xcopy "%STAGED%\app" "app\" /E /I /Y /Q >nul
if errorlevel 1 goto rollback

rmdir /s /q app.old
echo.
echo Update applied successfully. Relaunching game...
start "" python supervisor.py
exit /b 0

:rollback
echo.
echo Copy failed. Rolling back...
if exist app rmdir /s /q app
ren app.old app
if errorlevel 1 (
    echo ROLLBACK FAILED. Rename app.old back to app manually.
    pause
    exit /b 2
)
echo Rolled back to the previous version.
pause
exit /b 1

:usage
echo Usage: updater.bat ^<host_pid^> ^<staged_package_dir^>
pause
exit /b 1