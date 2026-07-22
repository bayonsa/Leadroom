$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Convert-ToWslPath([string]$Path) {
    $escaped = $Path.Replace('\', '\\')
    return (wsl -- wslpath -a $escaped).Trim()
}

$updateScript = Convert-ToWslPath (Join-Path $root "infra\osm\leadroom-osm-update.sh")
$service = Convert-ToWslPath (Join-Path $root "infra\osm\leadroom-osm-update.service")
$timer = Convert-ToWslPath (Join-Path $root "infra\osm\leadroom-osm-update.timer")

wsl -d Ubuntu -u root -- install -m 0755 $updateScript /usr/local/sbin/leadroom-osm-update
wsl -d Ubuntu -u root -- install -m 0644 $service /etc/systemd/system/leadroom-osm-update.service
wsl -d Ubuntu -u root -- install -m 0644 $timer /etc/systemd/system/leadroom-osm-update.timer
wsl -d Ubuntu -u root -- systemctl daemon-reload
wsl -d Ubuntu -u root -- systemctl enable --now leadroom-osm-update.timer
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -c "INSERT INTO leadroom_osm_metadata(key, value) VALUES ('update_status', 'idle'), ('update_message', 'Automatic nightly updates are configured.') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"

Write-Host "Automatic local-data updates are enabled."
wsl -d Ubuntu -u root -- systemctl list-timers leadroom-osm-update.timer --no-pager
