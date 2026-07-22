$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run the setup steps in README.md first."
}

& $python -m pytest --cov=app --cov-report=term-missing
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m ruff check app tests run_cli.py run_api.py benchmarks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m compileall -q app tests benchmarks run_cli.py run_api.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path (Join-Path $PSScriptRoot "..\frontend\node_modules")) {
    Push-Location (Join-Path $PSScriptRoot "..\frontend")
    try {
        & npm run lint
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & npm test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally { Pop-Location }
}

& $python -m app.preflight
exit $LASTEXITCODE
