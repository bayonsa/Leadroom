param(
    [string]$Region = "great-britain",
    [string]$DataDirectory = "D:\LeadroomData\osm",
    [switch]$Refresh
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pbf = Join-Path $DataDirectory "$Region-latest.osm.pbf"
$url = "https://download.geofabrik.de/europe/$Region-latest.osm.pbf"
New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null

function Convert-ToWslPath([string]$Path) {
    $escaped = $Path.Replace('\', '\\')
    return (wsl -- wslpath -a $escaped).Trim()
}

$wslPbf = Convert-ToWslPath $pbf
if ($Refresh -and (Test-Path -LiteralPath $pbf)) {
    $download = "$pbf.download"
    $wslDownload = Convert-ToWslPath $download
    Write-Host "Downloading a fresh snapshot from $url"
    wsl -d Ubuntu -- wget --progress=dot:giga -O $wslDownload $url
    Move-Item -LiteralPath $download -Destination $pbf -Force
} elseif (-not (Test-Path -LiteralPath $pbf)) {
    Write-Host "Downloading or resuming $url"
    wsl -d Ubuntu -- wget -c --progress=dot:giga -O $wslPbf $url
} else {
    Write-Host "Using existing snapshot $pbf"
}

$wslLua = Convert-ToWslPath (Join-Path $root "infra\osm\leadroom.lua")
$wslSql = Convert-ToWslPath (Join-Path $root "infra\osm\post-import.sql")

$cluster = @((wsl -d Ubuntu -u root -- pg_lsclusters --no-header | Select-Object -First 1) -split "\s+")
if ($cluster.Count -lt 2) { throw "No PostgreSQL cluster was found in WSL." }
wsl -d Ubuntu -u root -- pg_ctlcluster $cluster[0] $cluster[1] start
wsl -d Ubuntu -u root -- mkdir -p /opt/leadroom
wsl -d Ubuntu -u root -- install -m 0644 $wslLua /opt/leadroom/leadroom.lua
wsl -d Ubuntu -u postgres -- osm2pgsql --create --slim --number-processes 8 --cache 12288 --output flex --style /opt/leadroom/leadroom.lua --database leadroom_osm $wslPbf
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -f $wslSql
wsl -d Ubuntu -u postgres -- osm2pgsql-replication init -d leadroom_osm --osm-file $wslPbf
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -c "INSERT INTO leadroom_osm_metadata(key, value) VALUES ('region', '$Region') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"

& (Join-Path $PSScriptRoot "setup-local-updates.ps1")

Write-Host "OSM import completed with incremental updates enabled."
