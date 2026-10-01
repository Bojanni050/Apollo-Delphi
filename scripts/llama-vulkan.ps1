<#
  Runs llama.cpp's llama-server on the GPU (Vulkan) as the embedding server of the desktop app.

  Why: embedding on a CPU takes about 1.3 s per fragment with Jina code 1.5B (a folder of 100 documents = half an hour);
  on an AMD Radeon RX 7800 XT it takes 0.04 s (about 30 times faster). Docker Desktop cannot hand a Vulkan GPU to a
  container on Windows, so this runs the official Windows build directly.

    powershell -ExecutionPolicy Bypass -File scripts\llama-vulkan.ps1
    powershell -ExecutionPolicy Bypass -File scripts\llama-vulkan.ps1 -Model "C:\models\bge-m3-Q8_0.gguf" -Pooling cls
    powershell -ExecutionPolicy Bypass -File scripts\llama-vulkan.ps1 -Stop

  The first run downloads the official release (about 32 MB, github.com/ggml-org/llama.cpp) into
  %LOCALAPPDATA%\Apollo-Delphi\llama-vulkan and checks it against the SHA-256 that GitHub publishes for it. Then in the
  app (Instellingen > Embeddingmodel): Base URL  http://localhost:8082/v1  and the same model name as before.
  The same model on the GPU gives practically the same vectors (cosine 0.9998), so nothing has to be re-indexed.

  Kept ASCII-only on purpose: Windows PowerShell 5.1 misreads UTF-8 without BOM.
#>
param(
    # The GGUF to serve. Default: the Jina file the app downloads into backend\models.
    [string]$Model = '',
    [int]$Port = 8082,
    # last = Jina code model, cls = bge-m3, mean = many others (see the model card).
    [string]$Pooling = 'last',
    # A pinned llama.cpp release. Newer ones work too; the flags below were tested with this one.
    [string]$Tag = 'b11320',
    [switch]$Stop
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $env:LOCALAPPDATA 'Apollo-Delphi\llama-vulkan'
$exe = Join-Path $dir 'llama-server.exe'

if ($Stop) {
    Get-Process llama-server -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | Stop-Process -Force
    Write-Host 'Stopped.'
    return
}

if (-not $Model) { $Model = Join-Path $root 'backend\models\jina-code-embeddings-1.5b-Q8_0.gguf' }
if (-not (Test-Path $Model)) { throw "Model not found: $Model. Download it in the app first (Instellingen > Embeddingmodel > Downloaden), or pass -Model." }

# Already running on that port?
try {
    if ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/health" -TimeoutSec 2).StatusCode -eq 200) {
        Write-Host "llama-server already answers on port $Port. Base URL: http://localhost:$Port/v1" -ForegroundColor Green
        return
    }
} catch { }

if (-not (Test-Path $exe)) {
    New-Item -ItemType Directory -Force $dir | Out-Null
    $name = "llama-$Tag-bin-win-vulkan-x64.zip"
    $release = Invoke-RestMethod "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$Tag" -Headers @{ 'User-Agent' = 'apollo-delphi' }
    $asset = $release.assets | Where-Object { $_.name -eq $name }
    if (-not $asset) { throw "Release $Tag has no $name." }
    $zip = Join-Path $dir $name
    Write-Host "Downloading $name ($([math]::Round($asset.size / 1MB, 1)) MB) from github.com/ggml-org/llama.cpp ..."
    Invoke-WebRequest -UseBasicParsing $asset.browser_download_url -OutFile $zip
    $expected = ($asset.digest -replace '^sha256:', '').ToLower()
    $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if (-not $expected) { throw 'GitHub published no checksum for this file; refusing to use it.' }
    if ($actual -ne $expected) { Remove-Item $zip -Force; throw "Checksum mismatch (expected $expected, got $actual). The download was removed." }
    Write-Host 'Checksum OK.'
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    Remove-Item $zip -Force
}

# -c 4096 -np 1 --fit off: the default (a 32768-token context times 4 slots, and the memory "fit" step) made the Vulkan
# build hang while loading. Embedding fragments are a few hundred tokens, so a small context is all that is needed.
$serverArgs = @('-m', $Model, '--embeddings', '--pooling', $Pooling, '--host', '127.0.0.1', '--port', "$Port",
    '-ngl', '99', '-c', '4096', '-np', '1', '--fit', 'off')
$log = Join-Path $dir 'server.log'
Start-Process -FilePath $exe -ArgumentList $serverArgs -WorkingDirectory $dir -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(180)
$ok = $false
while ((Get-Date) -lt $deadline -and -not $ok) {
    Start-Sleep -Seconds 2
    try { $ok = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/health" -TimeoutSec 3).StatusCode -eq 200 } catch { }
}
if (-not $ok) { throw "llama-server did not become ready in 3 minutes. See $log.err" }
Write-Host "llama-server runs on the GPU. Base URL: http://localhost:$Port/v1   (stop it with -Stop)" -ForegroundColor Green
