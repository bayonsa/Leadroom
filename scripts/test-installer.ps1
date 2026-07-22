param(
    [string]$SetupPath = "",
    [int]$Port = 8877
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$build = (Resolve-Path (Join-Path $root "build")).Path
if (-not $SetupPath) { $SetupPath = Join-Path $root "dist\Leadroom-Setup.exe" }
$SetupPath = (Resolve-Path $SetupPath).Path
$smoke = Join-Path $build ("installer-smoke-" + [guid]::NewGuid().ToString("N"))
$app = Join-Path $smoke "app"
$data = Join-Path $smoke "data"
$downloads = Join-Path $smoke "downloads"
$backup = Join-Path $smoke "bootstrap-backup"
$bootstrap = Join-Path $env:LOCALAPPDATA "Leadroom"
$hadBootstrap = Test-Path -LiteralPath $bootstrap
$originalModels = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")

function Remove-TreeWithRetry([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force
            return
        } catch {
            if ($attempt -eq 9) { throw }
            Start-Sleep -Milliseconds (250 * ($attempt + 1))
        }
    }
}

function Stop-Leadroom {
    Get-Process Leadroom -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Force -Path $smoke | Out-Null
if ($hadBootstrap) { Copy-Item -LiteralPath $bootstrap -Destination $backup -Recurse -Force }

try {
    Stop-Leadroom
    $arguments = @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        "/DIR=$app", "/DATAROOT=$data", "/DOWNLOADSROOT=$downloads",
        "/INSTALL_WEBVIEW=0", "/INSTALL_OLLAMA=0", "/DOWNLOAD_MODEL=0",
        "/FORCE_STORAGE=1", "/LOG=$(Join-Path $build 'installer-smoke.log')"
    )
    $install = Start-Process -FilePath $SetupPath -ArgumentList $arguments -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw "Installer exited with $($install.ExitCode)." }
    foreach ($required in @("Leadroom.exe", "unins000.exe", "scripts\install-bootstrap.ps1")) {
        if (-not (Test-Path -LiteralPath (Join-Path $app $required))) {
            throw "Installed file is missing: $required"
        }
    }
    $storage = Get-Content (Join-Path $bootstrap "storage.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($storage.data_root) -ne [IO.Path]::GetFullPath($data)) {
        throw "Installer did not configure the selected data folder."
    }
    if ([IO.Path]::GetFullPath($storage.downloads_root) -ne [IO.Path]::GetFullPath($downloads)) {
        throw "Installer did not configure the selected downloads folder."
    }
    $env:LEAD_SCRAPER_NO_BROWSER = "1"
    $env:LEADROOM_PORT = [string]$Port
    Start-Process -FilePath (Join-Path $app "Leadroom.exe") -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(60)
    $health = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $health -or $health.status -ne "ok") { throw "Installed application health check failed." }
    Stop-Leadroom
    Remove-Item Env:LEAD_SCRAPER_NO_BROWSER
    Remove-Item Env:LEADROOM_PORT
    $uninstall = Start-Process -FilePath (Join-Path $app "unins000.exe") `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw "Uninstaller exited with $($uninstall.ExitCode)." }
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath (Join-Path $app "Leadroom.exe")) {
        throw "Uninstaller left Leadroom.exe behind."
    }
    Write-Host "Installer, installed-app health, and uninstaller smoke tests passed."
} finally {
    Stop-Leadroom
    Remove-Item Env:LEAD_SCRAPER_NO_BROWSER -ErrorAction SilentlyContinue
    Remove-Item Env:LEADROOM_PORT -ErrorAction SilentlyContinue
    [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $originalModels, "User")
    $uninstaller = Join-Path $app "unins000.exe"
    if (Test-Path -LiteralPath $uninstaller) {
        Start-Process -FilePath $uninstaller `
            -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait | Out-Null
    }
    if (Test-Path -LiteralPath $bootstrap) {
        $resolved = (Resolve-Path -LiteralPath $bootstrap).Path
        if ($resolved -ne [IO.Path]::GetFullPath($bootstrap)) { throw "Unsafe bootstrap cleanup path." }
        Remove-TreeWithRetry $resolved
    }
    if ($hadBootstrap -and (Test-Path -LiteralPath $backup)) {
        Move-Item -LiteralPath $backup -Destination $bootstrap
    }
    if (Test-Path -LiteralPath $smoke) {
        $resolved = (Resolve-Path -LiteralPath $smoke).Path
        if (-not $resolved.StartsWith($build, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe installer smoke cleanup path."
        }
        Remove-TreeWithRetry $resolved
    }
}
