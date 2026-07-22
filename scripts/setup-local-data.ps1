$ErrorActionPreference = "Stop"

Write-Host "Installing PostgreSQL, PostGIS and osm2pgsql in WSL2..."
wsl -d Ubuntu -u root -- bash -lc "DEBIAN_FRONTEND=noninteractive apt-get update -qq && apt-get install -y postgresql postgresql-contrib postgis postgresql-postgis osm2pgsql"
$cluster = @((wsl -d Ubuntu -u root -- pg_lsclusters --no-header | Select-Object -First 1) -split "\s+")
if ($cluster.Count -lt 2) { throw "PostgreSQL was installed but no WSL cluster was found." }
wsl -d Ubuntu -u root -- pg_ctlcluster $cluster[0] $cluster[1] start

$role = wsl -d Ubuntu -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='leadroom'"
if (-not $role) { wsl -d Ubuntu -u postgres -- createuser --login leadroom }
wsl -d Ubuntu -u postgres -- psql -c "ALTER ROLE leadroom WITH PASSWORD 'leadroom-local';"
$database = wsl -d Ubuntu -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='leadroom_osm'"
if (-not $database) { wsl -d Ubuntu -u postgres -- createdb --owner=leadroom leadroom_osm }
wsl -d Ubuntu -u postgres -- psql -d leadroom_osm -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pg_trgm;"

Write-Host "Local data engine is ready on postgresql://127.0.0.1:5432/leadroom_osm"
