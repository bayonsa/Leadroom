$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location (Join-Path $root "frontend")
try { & npm run build } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $root ".venv\Scripts\python.exe") -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name Leadroom `
    --icon "assets/leadroom-icon.ico" `
    --add-data "frontend/dist;frontend/dist" `
    --add-data "assets/leadroom-icon.ico;assets" `
    --collect-data tldextract `
    --collect-data undetected_playwright `
    --collect-all tiktoken `
    --collect-all psycopg `
    --collect-all psycopg_binary `
    --collect-all webview `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import tiktoken_ext.openai_public `
    --collect-all scrapegraphai `
    run_desktop.py
exit $LASTEXITCODE
