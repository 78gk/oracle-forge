param(
    [string]$ComposeFile = "mcp/docker-compose.yml",
    [switch]$SkipSeed,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

function Invoke-McpToolsList {
    param(
        [int]$TimeoutSec = 5
    )
    $body = @{
        jsonrpc = "2.0"
        id = "oracle-forge-mcp-check"
        method = "tools/list"
        params = @{}
    } | ConvertTo-Json -Depth 10

    return Invoke-RestMethod -Method Post -Uri "http://localhost:5000/mcp" -ContentType "application/json" -Body $body -TimeoutSec $TimeoutSec
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$composePath = Join-Path $repoRoot $ComposeFile
if (-not (Test-Path $composePath)) {
    throw "Compose file not found: $composePath"
}

Push-Location $repoRoot
try {
    Write-Host "Starting MongoDB and PostgreSQL containers..."
    docker compose -f $composePath up -d mongo postgres
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start mongo/postgres containers."
    }

    if (-not $SkipSeed) {
        Write-Host "Seeding MongoDB from DAB Yelp dump..."
        docker compose -f $composePath --profile seed run --rm mongo-seed
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to seed MongoDB from DAB Yelp dump."
        }
    }

    Write-Host "Starting MCP Toolbox..."
    docker compose -f $composePath up -d toolbox
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start MCP Toolbox container."
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-McpToolsList -TimeoutSec 3
            if ($resp.result.tools) {
                $ready = $true
                break
            }
        }
        catch {
            # wait and retry
        }
        Start-Sleep -Seconds 2
    }

    if (-not $ready) {
        throw "MCP Toolbox did not become ready on http://localhost:5000/mcp within $TimeoutSeconds seconds."
    }

    $toolNames = @()
    try {
        $payload = Invoke-McpToolsList -TimeoutSec 5
        $toolList = $payload.result.tools
        $toolNames = @($toolList | ForEach-Object { $_.name } | Where-Object { $_ })
    }
    catch {
        Write-Warning "MCP is reachable but tool list parsing failed: $($_.Exception.Message)"
    }

    Write-Host "MCP is ready at http://localhost:5000/mcp"
    if ($toolNames.Count -gt 0) {
        Write-Host "Discovered tools:"
        $toolNames | ForEach-Object { Write-Host " - $_" }
    }
}
finally {
    Pop-Location
}
