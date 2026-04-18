# End-to-end smoke: unified MCP health + optional Yelp eval (real DB + DAB).
# Prerequisites: Docker (postgres, mongo, mcp-server), DataAgentBench, .env with OPENROUTER_API_KEY.
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "=== 1) Unified MCP /health ===" -ForegroundColor Cyan
try {
    $h = Invoke-RestMethod -Uri "http://localhost:5000/health" -TimeoutSec 8
    $h | ConvertTo-Json -Depth 6
} catch {
    Write-Warning "MCP not reachable on http://localhost:5000/health. Start: docker compose -f mcp/docker-compose.yml up -d postgres mongo mcp-server"
    Write-Warning $_.Exception.Message
}

Write-Host "`n=== 2) Tool catalog (sample) ===" -ForegroundColor Cyan
try {
    $t = Invoke-RestMethod -Uri "http://localhost:5000/v1/tools" -TimeoutSec 8
    "total_count=$($t.total_count)"
} catch {
    Write-Warning $_.Exception.Message
}

$Dab = Join-Path $RepoRoot "DataAgentBench"
if (-not (Test-Path $Dab)) {
    Write-Warning "DataAgentBench not found at $Dab — skipping eval. Clone DAB and run git lfs pull."
    exit 0
}

Write-Host "`n=== 3) Eval smoke: yelp query1, 1 trial ===" -ForegroundColor Cyan
$env:DAB_TRIALS_PER_QUERY = "1"
$env:PYTHONPATH = "$RepoRoot"
& python -m eval.harness --datasets yelp --query_ids 1 --n_trials 1
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "`nDone. See eval/results.json and eval/latest.json" -ForegroundColor Green
