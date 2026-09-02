$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot
$compose = @(
    "compose",
    "-f", (Join-Path $projectDir "docker-compose.yml"),
    "-f", (Join-Path $projectDir "docker-compose.tailscale.override.yml"),
    "--profile", "tailscale"
)

Push-Location $projectDir
try {
    if (-not (Test-Path ".env")) {
        throw ".env не найден. Создайте его и задайте TAILSCALE_AUTH_KEY."
    }
    if (-not (Select-String -Path ".env" -Pattern '^TAILSCALE_AUTH_KEY=.+')) {
        throw "TAILSCALE_AUTH_KEY не задан в .env."
    }

    Write-Host "Запускаем стек с Tailscale..."
    docker @compose up -d

    Write-Host "Ждем готовности Tailscale..."
    $ready = $false
    1..30 | ForEach-Object {
        if (-not $ready) {
            docker @compose exec -T tailscale tailscale status *> $null
            $ready = ($LASTEXITCODE -eq 0)
            if (-not $ready) { Start-Sleep -Seconds 2 }
        }
    }
    if (-not $ready) { throw "Tailscale не стал активным за 60 секунд. Выполните: docker compose logs tailscale" }

    Write-Host "Включаем HTTPS для панели..."
    docker @compose exec -T tailscale tailscale serve --bg https / http://localhost:8000

    $status = (docker @compose exec -T tailscale tailscale status --json | Out-String) | ConvertFrom-Json
    $magicName = $status.Self.DNSName.TrimEnd('.')
    Write-Host "Готово. Панель доступна внутри tailnet: https://$magicName/"
}
finally {
    Pop-Location
}