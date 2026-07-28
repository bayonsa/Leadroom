param(
    [string]$ResourceDirectory = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($ResourceDirectory)) {
    $ResourceDirectory = Join-Path $root "infra\osm"
}

function Assert-NativeSuccess([string]$Operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Convert-ToWslPath([string]$Path) {
    $escaped = $Path.Replace('\', '\\')
    $converted = wsl -- wslpath -a $escaped
    Assert-NativeSuccess "Converting an update resource path for WSL"
    return $converted.Trim()
}

$updateScript = Convert-ToWslPath (Join-Path $ResourceDirectory "leadroom-osm-update.sh")
$service = Convert-ToWslPath (Join-Path $ResourceDirectory "leadroom-osm-update.service")
$timer = Convert-ToWslPath (Join-Path $ResourceDirectory "leadroom-osm-update.timer")

wsl -d Ubuntu -u root -- install -m 0755 $updateScript /usr/local/sbin/leadroom-osm-update
Assert-NativeSuccess "Installing the map update script"
wsl -d Ubuntu -u root -- install -m 0644 $service /etc/systemd/system/leadroom-osm-update.service
Assert-NativeSuccess "Installing the map update service"
wsl -d Ubuntu -u root -- install -m 0644 $timer /etc/systemd/system/leadroom-osm-update.timer
Assert-NativeSuccess "Installing the map update timer"
wsl -d Ubuntu -u root -- systemctl daemon-reload
Assert-NativeSuccess "Reloading WSL services"
wsl -d Ubuntu -u root -- systemctl enable --now leadroom-osm-update.timer
Assert-NativeSuccess "Enabling automatic map updates"
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -c "INSERT INTO leadroom_osm_metadata(key, value) VALUES ('update_status', 'idle'), ('update_message', 'Automatic nightly updates are configured.') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"
Assert-NativeSuccess "Recording the automatic update status"

Write-Host "Automatic local-data updates are enabled."
wsl -d Ubuntu -u root -- systemctl list-timers leadroom-osm-update.timer --no-pager
Assert-NativeSuccess "Verifying the automatic map update timer"
