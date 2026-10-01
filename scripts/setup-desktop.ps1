<#
  One-time setup for the desktop app: a virtualenv with the backend's packages (.venv at the repository root),
  the frontend's packages and its production build (the desktop app serves frontend\dist), and the Tauri CLI.
  Safe to run again: it only installs what changed.

  Needs: Python 3.11+, Node.js, Rust (rustup) with the MSVC build tools, and git (werkmappen are git repositories).
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Need($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "$name was not found. $hint" }
}
function Run([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$exe $($arguments -join ' ') failed (exit code $LASTEXITCODE)" }
}

Need 'git' 'Install Git for Windows: https://git-scm.com/download/win'
Need 'node' 'Install Node.js: https://nodejs.org/'
Need 'cargo' 'Install Rust: https://rustup.rs/ (with the MSVC build tools)'
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { throw 'Python was not found. Install Python 3.11+: https://www.python.org/' }

Step 'Python environment (.venv)'
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    if ($python -eq 'py') { Run 'py' @('-3', '-m', 'venv', '.venv') } else { Run 'python' @('-m', 'venv', '.venv') }
}
Run '.venv\Scripts\python.exe' @('-m', 'pip', 'install', '--quiet', '--upgrade', 'pip')
Run '.venv\Scripts\python.exe' @('-m', 'pip', 'install', '--quiet', '-r', 'backend\requirements.txt')

Step 'Frontend (packages and production build)'
Run 'npm' @('--prefix', 'frontend', 'install')
Run 'npm' @('--prefix', 'frontend', 'run', 'build')

Step 'Tauri CLI'
Run 'npm' @('install')

Write-Host "`nDone. Start the desktop app with:  npm run desktop" -ForegroundColor Green
