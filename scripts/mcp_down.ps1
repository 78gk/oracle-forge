param(
    [string]$ComposeFile = "mcp/docker-compose.yml",
    [switch]$RemoveVolumes
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$composePath = Join-Path $repoRoot $ComposeFile
if (-not (Test-Path $composePath)) {
    throw "Compose file not found: $composePath"
}

Push-Location $repoRoot
try {
    $args = @("compose", "-f", $composePath, "down")
    if ($RemoveVolumes) {
        $args += "-v"
    }
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stop docker compose stack."
    }
}
finally {
    Pop-Location
}
