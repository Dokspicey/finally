# Stop and remove the FinAlly container (Windows PowerShell).
# The host `db\` directory is left untouched so SQLite state persists.

$ErrorActionPreference = 'Stop'

$ContainerName = 'finally'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker is not installed or not on PATH.'
    exit 1
}

$Existing = docker ps -a --format '{{.Names}}' | Where-Object { $_ -eq $ContainerName }
if ($Existing) {
    Write-Host "Stopping $ContainerName..."
    docker rm -f $ContainerName | Out-Null
    Write-Host 'Stopped.'
} else {
    Write-Host "No $ContainerName container is running."
}
