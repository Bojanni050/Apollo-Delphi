@echo off
rem ============================================================================
rem  Apollo Delphi - de desktop-app starten
rem
rem  Dubbelklik op dit bestand, of typ in een terminal (met .\ ervoor):   .\start.cmd
rem
rem    .\start.cmd          eerst nieuwe code ophalen (git pull), dan de app starten
rem    .\start.cmd setup    alleen instellen of bijwerken, zonder de app te starten
rem    .\start.cmd noupdate  de app starten zonder eerst git pull te draaien
rem
rem  De eerste keer maakt het een .venv aan, installeert de pakketten en bouwt de
rem  frontend (scripts\setup-desktop.ps1). Daarna opent het de app (npm run desktop).
rem  Het eerste keer starten compileert ook het Rust-venster: dat duurt een paar
rem  minuten. Daarna gaat het snel. Sluit je het venster, dan stopt ook de backend.
rem
rem  Nodig: Python 3.11+, Node.js, git, Rust (rustup) met de MSVC build tools.
rem
rem  Embeddings: bij het starten draait scripts\llama-vulkan.ps1 de embedding-server op de GPU
rem  (poort 8082; zie de README). Zet in de app de Base URL op http://localhost:8082/v1.
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

rem Nieuwe code ophalen voor het starten (staat op GitHub). Lukt het niet (geen internet,
rem lokale wijzigingen), dan start de app gewoon met wat er nu staat. Overslaan: .\start.cmd noupdate
if /i "%~1"=="noupdate" goto run
echo.
echo == Nieuwe code ophalen (git pull) ==
git pull --ff-only
if errorlevel 1 (
    echo.
    echo Git pull lukte niet; de app start met de code die er nu staat.
)
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
rem De embedding-server op de GPU (Vulkan). Draait hij al, dan kost dit niets; ontbreekt het model of lukt het niet,
rem dan start de app gewoon. Overslaan: zet APOLLO_LLAMA=0. Stoppen: scripts\llama-vulkan.ps1 -Stop
if not "%APOLLO_LLAMA%"=="0" (
    echo.
    echo == Embedding-server controleren ==
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\llama-vulkan.ps1" -Optional
)

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
