$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "check.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$api = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/health"
if ($api.status -ne "ok") { throw "Local API health check failed." }

$healthSamples = 1..10 | ForEach-Object {
    (Measure-Command { Invoke-RestMethod "http://127.0.0.1:8000/api/v1/health" | Out-Null }).TotalMilliseconds
}
$healthP95 = ($healthSamples | Sort-Object)[9]
if ($healthP95 -gt 250) { throw "Health API exceeded 250 ms budget: $healthP95 ms." }

$uiStatus = & curl.exe -s -o NUL -w "%{http_code}" "http://127.0.0.1:5173"
if ($uiStatus -ne "200") { throw "Frontend health check failed with HTTP $uiStatus." }

Push-Location (Join-Path $PSScriptRoot "..\frontend")
try { & npm run test:e2e } finally { Pop-Location }
exit $LASTEXITCODE
