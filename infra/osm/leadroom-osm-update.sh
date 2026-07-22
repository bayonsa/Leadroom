#!/usr/bin/env bash
set -Eeuo pipefail

DATABASE="leadroom_osm"
LOCK_FILE="/var/lock/leadroom-osm-update.lock"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 0
fi

metadata() {
    local key="$1"
    local value="$2"
    psql -d "$DATABASE" -v ON_ERROR_STOP=1 -v key="$key" -v value="$value" <<'SQL'
INSERT INTO leadroom_osm_metadata(key, value)
VALUES (:'key', :'value')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
SQL
}

failed() {
    local code=$?
    metadata update_status failed || true
    metadata update_message "Update failed. Review journalctl -u leadroom-osm-update.service." || true
    exit "$code"
}
trap failed ERR

metadata update_status running
metadata update_message "Downloading and applying OpenStreetMap changes."

osm2pgsql-replication update -d "$DATABASE" --max-diff-size 256

metadata last_updated_at "$(date --iso-8601=seconds)"
metadata update_status idle
metadata update_message "Local OpenStreetMap data is current."
