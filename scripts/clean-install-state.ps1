param(
    [switch]$IncludeWorkspaceData,
    [switch]$IncludeDownloads,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
$bootstrapRoot = Join-Path $env:LOCALAPPDATA "Leadroom"
$configPath = Join-Path $bootstrapRoot "storage.json"

if (-not $Confirm) {
    throw "Cleanup is destructive. Rerun with -Confirm after reviewing the selected paths."
}

function Assert-SafePath([string]$Value) {
    $path = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Value))
    $root = [IO.Path]::GetPathRoot($path)
    $blocked = @(
        $root,
        [IO.Path]::GetFullPath($env:USERPROFILE),
        [IO.Path]::GetFullPath($env:LOCALAPPDATA),
        [IO.Path]::GetFullPath($env:APPDATA),
        [IO.Path]::GetFullPath($env:ProgramFiles)
    )
    if ($path.Length -lt 8 -or $blocked -contains $path.TrimEnd('\')) {
        throw "Refusing to clean unsafe path: $path"
    }
    return $path
}

function Remove-KnownItem([string]$Path, [switch]$Recursive) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $safe = Assert-SafePath $Path
    if ($Recursive) { Remove-Item -LiteralPath $safe -Recurse -Force }
    else { Remove-Item -LiteralPath $safe -Force }
}

Get-Process Leadroom -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

$storage = @{}
if (Test-Path -LiteralPath $configPath) {
    try { $storage = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { Write-Warning "Storage configuration could not be read; only bootstrap files will be removed." }
}

if ($IncludeWorkspaceData -and $storage.data_root) {
    $dataRoot = Assert-SafePath ([string]$storage.data_root)
    foreach ($name in @("lead_scraper.db", "lead_scraper.db-wal", "lead_scraper.db-shm")) {
        Remove-KnownItem (Join-Path $dataRoot $name)
    }
    Remove-KnownItem (Join-Path $dataRoot "exports") -Recursive
}

if ($IncludeDownloads -and $storage.downloads_root) {
    $downloadsRoot = Assert-SafePath ([string]$storage.downloads_root)
    foreach ($name in @("cache", "playwright", "ollama", "osm")) {
        Remove-KnownItem (Join-Path $downloadsRoot $name) -Recursive
    }
}

Remove-KnownItem $bootstrapRoot -Recursive
Write-Host "Leadroom runtime state was removed. Application source and release artifacts were not touched."
