CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS leadroom_osm_search_trgm
    ON leadroom_osm_businesses USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS leadroom_osm_location_trgm
    ON leadroom_osm_businesses USING gin (location_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS leadroom_osm_geom
    ON leadroom_osm_businesses USING gist (geom);
CREATE INDEX IF NOT EXISTS leadroom_osm_contact
    ON leadroom_osm_businesses ((website <> ''), (phone <> ''), (email <> ''));
CREATE INDEX IF NOT EXISTS leadroom_osm_places_search_trgm
    ON leadroom_osm_places USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS leadroom_osm_places_geom
    ON leadroom_osm_places USING gist (geom);

CREATE TABLE IF NOT EXISTS leadroom_osm_metadata (
    key text PRIMARY KEY,
    value text NOT NULL
);
INSERT INTO leadroom_osm_metadata(key, value)
VALUES ('last_imported_at', now()::text)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

ANALYZE leadroom_osm_businesses;
ANALYZE leadroom_osm_places;

GRANT SELECT ON leadroom_osm_businesses TO leadroom;
GRANT SELECT ON leadroom_osm_places TO leadroom;
GRANT SELECT ON leadroom_osm_metadata TO leadroom;
