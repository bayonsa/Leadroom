param(
    [string]$Region = "great-britain",
    [string]$DataDirectory = "D:\LeadroomData\osm",
    [string]$ResourceDirectory = "",
    [string]$UpdateScriptPath = "",
    [switch]$Refresh
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($ResourceDirectory)) {
    $ResourceDirectory = Join-Path $root "infra\osm"
}
if ([string]::IsNullOrWhiteSpace($UpdateScriptPath)) {
    $UpdateScriptPath = Join-Path $PSScriptRoot "setup-local-updates.ps1"
}
$pbf = Join-Path $DataDirectory "$Region-latest.osm.pbf"
$url = "https://download.geofabrik.de/europe/$Region-latest.osm.pbf"
New-Item -ItemType Directory -Force -Path $DataDirectory | Out-Null

function Assert-NativeSuccess([string]$Operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Convert-ToWslPath([string]$Path) {
    $escaped = $Path.Replace('\', '\\')
    $converted = wsl -- wslpath -a $escaped
    Assert-NativeSuccess "Converting a Windows path for WSL"
    return $converted.Trim()
}

$wslPbf = Convert-ToWslPath $pbf
if ($Refresh -and (Test-Path -LiteralPath $pbf)) {
    $download = "$pbf.download"
    $wslDownload = Convert-ToWslPath $download
    Write-Host "Downloading a fresh snapshot from $url"
    wsl -d Ubuntu -- wget --progress=dot:giga -O $wslDownload $url
    Assert-NativeSuccess "Downloading the OpenStreetMap snapshot"
    Move-Item -LiteralPath $download -Destination $pbf -Force
} elseif (-not (Test-Path -LiteralPath $pbf)) {
    Write-Host "Downloading or resuming $url"
    wsl -d Ubuntu -- wget -c --progress=dot:giga -O $wslPbf $url
    Assert-NativeSuccess "Downloading the OpenStreetMap snapshot"
} else {
    Write-Host "Using existing snapshot $pbf"
}

$wslLua = Convert-ToWslPath (Join-Path $ResourceDirectory "leadroom.lua")
$wslSql = Convert-ToWslPath (Join-Path $ResourceDirectory "post-import.sql")

$cluster = @((wsl -d Ubuntu -u root -- pg_lsclusters --no-header | Select-Object -First 1) -split "\s+")
Assert-NativeSuccess "Finding the PostgreSQL cluster"
if ($cluster.Count -lt 2) { throw "No PostgreSQL cluster was found in WSL." }
wsl -d Ubuntu -u root -- pg_ctlcluster $cluster[0] $cluster[1] start
Assert-NativeSuccess "Starting PostgreSQL"
wsl -d Ubuntu -u root -- mkdir -p /opt/leadroom
Assert-NativeSuccess "Preparing Leadroom resources in WSL"
wsl -d Ubuntu -u root -- install -m 0644 $wslLua /opt/leadroom/leadroom.lua
Assert-NativeSuccess "Installing the OpenStreetMap import style"
wsl -d Ubuntu -u postgres -- osm2pgsql --create --slim --number-processes 8 --cache 12288 --output flex --style /opt/leadroom/leadroom.lua --database leadroom_osm $wslPbf
Assert-NativeSuccess "Importing OpenStreetMap data"
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -f $wslSql
Assert-NativeSuccess "Creating the Leadroom map schema"
wsl -d Ubuntu -u postgres -- osm2pgsql-replication init -d leadroom_osm --osm-file $wslPbf
Assert-NativeSuccess "Initializing incremental map updates"
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -c "INSERT INTO leadroom_osm_metadata(key, value) VALUES ('region', '$Region') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"
Assert-NativeSuccess "Recording the map region"

& $UpdateScriptPath -ResourceDirectory $ResourceDirectory
if (-not $?) { throw "Configuring automatic map updates failed." }

Write-Host "OSM import completed with incremental updates enabled."
