param(
    [string]$ComposeFile = "mcp/docker-compose.yml"
)

$ErrorActionPreference = "Stop"

function Invoke-McpToolsList {
    param(
        [int]$TimeoutSec = 5
    )
    $body = @{
        jsonrpc = "2.0"
        id = "oracle-forge-mcp-status"
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
    Write-Host "Docker compose service status:"
    docker compose -f $composePath ps
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query docker compose service status."
    }

    Write-Host ""
    Write-Host "Checking MCP endpoint..."
    try {
        $payload = Invoke-McpToolsList -TimeoutSec 5
        $toolList = $payload.result.tools
        $names = @($toolList | ForEach-Object { $_.name } | Where-Object { $_ })
        $requiredTools = @(
            "mongodb_aggregate_business",
            "postgres_sql_query"
        )
        $missing = @($requiredTools | Where-Object { $_ -notin $names })
        Write-Host "MCP reachable: YES"
        Write-Host "Tool count: $($names.Count)"
        $names | ForEach-Object { Write-Host " - $_" }
        if ($missing.Count -gt 0) {
            Write-Host "Missing required tools: $($missing -join ', ')"
            exit 1
        }
    }
    catch {
        Write-Host "MCP reachable: NO"
        Write-Host "Reason: $($_.Exception.Message)"
        exit 1
    }
}
finally {
    Pop-Location
}
