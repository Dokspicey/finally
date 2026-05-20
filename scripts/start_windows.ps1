# Start the FinAlly container (Windows PowerShell).
#
# Usage:
#   scripts\start_windows.ps1           # build image if missing, then run
#   scripts\start_windows.ps1 -Build    # force rebuild before run
#
# Idempotent: removes any existing `finally` container before starting a new one.

[CmdletBinding()]
param(
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

$ImageName     = 'finally:latest'
$ContainerName = 'finally'
$Port          = if ($env:FINALLY_PORT) { $env:FINALLY_PORT } else { '8000' }

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker is not installed or not on PATH.'
    exit 1
}

$EnvFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env not found at $EnvFile. Copy .env.example to .env and fill in your keys."
    exit 1
}

$DbDir = Join-Path $RepoRoot 'db'
if (-not (Test-Path $DbDir)) {
    New-Item -ItemType Directory -Path $DbDir | Out-Null
}

function Test-ImageExists {
    docker image inspect $ImageName *> $null
    return $LASTEXITCODE -eq 0
}

if ($Build -or -not (Test-ImageExists)) {
    Write-Host "Building image $ImageName..."
    docker build -t $ImageName $RepoRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Existing = docker ps -a --format '{{.Names}}' | Where-Object { $_ -eq $ContainerName }
if ($Existing) {
    Write-Host "Removing existing container $ContainerName..."
    docker rm -f $ContainerName | Out-Null
}

Write-Host "Starting $ContainerName on port $Port..."
docker run -d `
    --name $ContainerName `
    -v "${RepoRoot}/db:/app/db" `
    -p "${Port}:8000" `
    --env-file $EnvFile `
    $ImageName | Out-Null

Write-Host ''
Write-Host "FinAlly is starting at: http://localhost:$Port"
Write-Host "Health check:           http://localhost:$Port/api/health"
Write-Host "Logs:                   docker logs -f $ContainerName"
Write-Host "Stop:                   scripts\stop_windows.ps1"
