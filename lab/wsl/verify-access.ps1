# Verify browser access from Windows, rather than only from inside WSL.
# Output contains public status information only; never exports a kubeconfig.
param([string]$EvidencePath)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { throw 'Missing dependency: curl.exe' }

function Get-LocalResponse {
    param([string]$Path, [int]$Port = 8080, [string]$Accept = 'application/json')
    $cliArgs = @('--noproxy', '*', '--fail', '--silent', '--show-error', '--max-time', '15',
                 '-H', "Accept: $Accept", "http://127.0.0.1:$Port$Path")
    $responseBody = @(& curl.exe @cliArgs) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Local HTTP check failed: port $Port, path $Path" }
    return $responseBody
}

$html = Get-LocalResponse -Path '/applications' -Accept 'text/html'
if ($html -notmatch '<title>Argo CD</title>') { throw 'Expected Argo CD HTML.' }
$bundle = [regex]::Match($html, 'src="(main\.[a-f0-9]+\.js)"').Groups[1].Value
if (-not $bundle) { throw 'Missing Argo CD JavaScript bundle reference.' }
$javascript = Get-LocalResponse -Path "/$bundle" -Accept 'application/javascript'
if ($javascript.Length -lt 1000) { throw 'Unexpected dashboard JavaScript response.' }
$version = Get-LocalResponse -Path '/api/version' | ConvertFrom-Json
if ($version.Version -ne 'v3.5.3') { throw 'Unexpected dashboard version.' }
$null = Get-LocalResponse -Path '/api/v1/settings' | ConvertFrom-Json
$null = Get-LocalResponse -Path '/api/v1/projects' | ConvertFrom-Json
$applications = Get-LocalResponse -Path '/api/v1/applications' | ConvertFrom-Json
$labApplication = @($applications.items | Where-Object { $_.metadata.name -eq 'vcloud-wsl-platform' })
if ($labApplication.Count -ne 1) { throw 'The expected local lab Application is absent from the API.' }
if ((Get-LocalResponse -Path '/' -Port 18080 -Accept 'text/plain').Trim() -ne 'vcloud-wsl-ok') {
    throw 'Unexpected lab HTTP smoke response.'
}

$evidence = [ordered]@{
    checkedAtUtc = [DateTime]::UtcNow.ToString('o')
    origin = 'Windows loopback'
    ui = 'http://127.0.0.1:8080/'
    smoke = 'http://127.0.0.1:18080/'
    accessPassed = $true
    checks = @('HTML route', 'JavaScript bundle', 'version API', 'settings API', 'projects API', 'applications API', 'HTTP smoke body')
    application = [ordered]@{
        name = $labApplication[0].metadata.name
        sync = $labApplication[0].status.sync.status
        health = $labApplication[0].status.health.status
    }
}
if (-not $EvidencePath) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
    $EvidencePath = Join-Path $repoRoot '.build/service-access/access-validation.json'
}
$null = New-Item -ItemType Directory -Force -Path (Split-Path $EvidencePath -Parent)
$evidence | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $EvidencePath -Encoding UTF8
Write-Output "PASS: dashboard HTML, assets and APIs; HTTP smoke body (Windows). Evidence: $EvidencePath"
Write-Output "GitOps is a separate gate: sync=$($evidence.application.sync), health=$($evidence.application.health)."
