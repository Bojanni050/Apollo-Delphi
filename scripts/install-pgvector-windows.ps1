<#
  Builds the pgvector extension from its official source (https://github.com/pgvector/pgvector) with the MSVC
  build tools and installs it into a local PostgreSQL, because there is no official Windows download.

  Run it in an ELEVATED PowerShell (Run as administrator): copying into "C:\Program Files\PostgreSQL" needs it.
  Nothing in the database changes yet; afterwards run  CREATE EXTENSION vector;  or just start Apollo, whose
  first migration does that (as the database owner or a superuser).

    powershell -ExecutionPolicy Bypass -File scripts\install-pgvector-windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install-pgvector-windows.ps1 -PgRoot "C:\Program Files\PostgreSQL\17"

  Needs: git and the "Desktop development with C++" (MSVC) build tools. If -SourceDir already holds a build
  (vector.dll), it is installed as it is.
#>
param(
    # Default: the newest PostgreSQL under C:\Program Files\PostgreSQL.
    [string]$PgRoot = '',
    [string]$Version = 'v0.8.6',
    [string]$SourceDir = (Join-Path $env:TEMP 'pgvector-build')
)
$ErrorActionPreference = 'Stop'

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run this in an elevated PowerShell (Run as administrator): it copies into the PostgreSQL folder.' }

if (-not $PgRoot) {
    $PgRoot = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin\pg_config.exe') } |
        Sort-Object { [int]($_.Name -replace '\D', '0') } -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $PgRoot -or -not (Test-Path (Join-Path $PgRoot 'bin\pg_config.exe'))) { throw "No PostgreSQL found. Pass -PgRoot (the folder that contains bin\pg_config.exe)." }
Write-Host "PostgreSQL: $PgRoot"

if (-not (Test-Path (Join-Path $SourceDir 'vector.dll'))) {
    if (-not (Test-Path (Join-Path $SourceDir 'Makefile.win'))) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git was not found.' }
        git clone --quiet --depth 1 --branch $Version https://github.com/pgvector/pgvector.git $SourceDir 2>$null
        if ($LASTEXITCODE -ne 0) { throw "Could not fetch pgvector $Version." }
    }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw 'The MSVC build tools were not found (Visual Studio Installer > Desktop development with C++).' }
    $vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
    Write-Host "Building pgvector $Version ..."
    cmd /c "call `"$vcvars`" >nul && set `"PGROOT=$PgRoot`" && cd /d `"$SourceDir`" && nmake /nologo /F Makefile.win"
    if (-not (Test-Path (Join-Path $SourceDir 'vector.dll'))) { throw 'The build did not produce vector.dll.' }
}

$ext = Join-Path $PgRoot 'share\extension'
Copy-Item (Join-Path $SourceDir 'vector.dll') (Join-Path $PgRoot 'lib') -Force
Copy-Item (Join-Path $SourceDir 'vector.control') $ext -Force
Copy-Item (Join-Path $SourceDir 'sql\vector--*.sql') $ext -Force
Write-Host "Installed vector.dll, vector.control and the SQL scripts into $PgRoot" -ForegroundColor Green
Write-Host 'Next: create a database for Apollo and put its URL in backend\.env (see the README, "Desktop app").'
