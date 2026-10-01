@echo off
rem ============================================================================
rem  Apollo Delphi - de desktop-app starten
rem
rem  Dubbelklik op dit bestand, of typ in een terminal (met .\ ervoor):   .\start.cmd
rem
rem    .\start.cmd          start de app (bij de eerste keer eerst alles instellen)
rem    .\start.cmd setup    alleen instellen of bijwerken, zonder de app te starten
rem
rem  De eerste keer maakt het een .venv aan, installeert de pakketten en bouwt de
rem  frontend (scripts\setup-desktop.ps1). Daarna opent het de app (npm run desktop).
rem  Het eerste keer starten compileert ook het Rust-venster: dat duurt een paar
rem  minuten. Daarna gaat het snel. Sluit je het venster, dan stopt ook de backend.
rem
rem  Nodig: Python 3.11+, Node.js, git, Rust (rustup) met de MSVC build tools.
rem
rem  Database: standaard SQLite in %LOCALAPPDATA%\Apollo-Delphi. Voor een lokale
rem  PostgreSQL zet je in backend\.env:
rem     DATABASE_URL=postgresql+psycopg2://gebruiker:wachtwoord@localhost:5432/apollo_desktop
rem  De database wordt zo nodig zelf aangemaakt; pgvector moet in die server staan
rem  (scripts\install-pgvector-windows.ps1, als administrator).
rem ============================================================================
setlocal
cd /d "%~dp0"

if /i "%~1"=="setup" goto setup
if not exist ".venv\Scripts\python.exe" goto setup
if not exist "frontend\node_modules" goto setup
if not exist "node_modules\@tauri-apps" goto setup
goto run

:setup
echo.
echo == Instellen (dit hoeft maar een keer) ==
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\setup-desktop.ps1"
if errorlevel 1 goto failed
if /i "%~1"=="setup" (
    echo.
    echo Klaar. Start de app met: .\start.cmd
    pause
    exit /b 0
)

:run
echo.
echo == Apollo wordt gestart ==
call npm run desktop
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo Het starten is mislukt: zie de melding hierboven.
pause
exit /b 1
