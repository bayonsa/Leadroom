from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from typing import Any

from app.filters import domain_key

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # The app remains usable before the optional local engine is installed.
    psycopg = None
    dict_row = None


DEFAULT_OSM_DATABASE_URL = "postgresql://leadroom:leadroom-local@127.0.0.1:5432/leadroom_osm"
NICHE_ALIASES = {
    "beauty": ("beauty", "hairdresser", "salon"),
    "hair": ("hairdresser", "beauty", "salon"),
    "salon": ("salon", "hairdresser", "beauty"),
    "cafe": ("cafe", "coffee shop"),
    "cafes": ("cafe", "coffee shop"),
    "dental": ("dentist", "dental"),
    "dentist": ("dentist", "dental"),
    "hvac": ("hvac", "air conditioning", "heating", "ventilation"),
    "air conditioning": ("air conditioning", "hvac", "ventilation"),
}
NICHE_QUALIFIERS = {
    "business",
    "businesses",
    "contractor",
    "contractors",
    "independent",
    "local",
    "provider",
    "providers",
    "service",
    "services",
}


class LocalDataService:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("OSM_DATABASE_URL", DEFAULT_OSM_DATABASE_URL)

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "engine": "PostgreSQL + PostGIS",
            "dataset": "OpenStreetMap Great Britain",
            "ready": False,
            "database": "offline",
            "businesses": 0,
            "with_website": 0,
            "with_phone": 0,
            "with_email": 0,
            "last_imported_at": None,
            "last_updated_at": None,
            "update_status": "not_configured",
            "update_message": "Automatic updates are not configured.",
            "update_schedule": "Daily at 03:30",
            "message": "The local data engine is not connected.",
        }
        if psycopg is None:
            result["message"] = "Install psycopg to connect to the local data engine."
            return result
        if self._use_wsl_bridge:
            return self._wsl_status(result)
        started = time.perf_counter()
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version() AS version")
                postgis = cursor.fetchone()["version"]
                cursor.execute("SELECT to_regclass('public.leadroom_osm_businesses') AS table_name")
                if not cursor.fetchone()["table_name"]:
                    result.update(
                        database="online",
                        postgis_version=postgis,
                        latency_ms=round((time.perf_counter() - started) * 1000),
                        message="Engine ready. Import an OSM dataset to begin local discovery.",
                    )
                    return result
                cursor.execute(
                    """
                    SELECT count(*) AS businesses,
                           count(*) FILTER (WHERE website <> '') AS with_website,
                           count(*) FILTER (WHERE phone <> '') AS with_phone,
                           count(*) FILTER (WHERE email <> '') AS with_email
                    FROM leadroom_osm_businesses
                    """
                )
                counts = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT json_build_object(
                        'last_imported_at', max(value) FILTER (WHERE key = 'last_imported_at'),
                        'last_updated_at', max(value) FILTER (WHERE key = 'last_updated_at'),
                        'update_status', coalesce(
                            max(value) FILTER (WHERE key = 'update_status'), 'not_configured'
                        ),
                        'update_message', coalesce(
                            max(value) FILTER (WHERE key = 'update_message'),
                            'Automatic updates are not configured.'
                        )
                    ) AS metadata
                    FROM leadroom_osm_metadata
                    """
                )
                imported = cursor.fetchone()
                result.update(
                    ready=counts["businesses"] > 0,
                    database="online",
                    postgis_version=postgis,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    **(imported["metadata"] if imported else {}),
                    message=(
                        "Local discovery is ready."
                        if counts["businesses"] > 0
                        else "Engine ready. Import an OSM dataset to begin local discovery."
                    ),
                    **counts,
                )
                return result
        except Exception as exc:
            result["message"] = str(exc).splitlines()[0][:240]
            return result

    def search(self, niche: str, location: str, limit: int, offset: int = 0) -> list[dict[str, str]]:
        if psycopg is None:
            raise RuntimeError("The local data engine requires psycopg")
        niche_terms = _expand_niche(niche)
        location_term = " ".join(
            re.sub(r"\b(?:uk|united kingdom)\b", " ", location.casefold())
            .translate(str.maketrans({",": " ", ".": " ", "-": " "}))
            .split()
        )
        if self._use_wsl_bridge:
            return self._wsl_search(niche_terms, location_term, limit, offset)
        niche_parameters = {f"niche_{index}": term for index, term in enumerate(niche_terms)}
        niche_rank = ", ".join(
            part
            for index in range(len(niche_terms))
            for part in (
                f"similarity(business.search_text, %(niche_{index})s)",
                f"word_similarity(%(niche_{index})s, business.search_text)",
            )
        )
        niche_match = " OR ".join(
            f"%(niche_{index})s <%% business.search_text "
            f"OR business.search_text ILIKE '%%' || %(niche_{index})s || '%%'"
            for index in range(len(niche_terms))
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH matching_places AS MATERIALIZED (
                    SELECT place.geom,
                           greatest(similarity(place.search_text, %(location)s),
                                    word_similarity(%(location)s, place.search_text)) AS rank
                    FROM leadroom_osm_places AS place
                    WHERE %(location)s <> ''
                      AND ST_Dimension(place.geom) >= 2
                      AND (%(location)s <%% place.search_text
                           OR place.search_text ILIKE '%%' || %(location)s || '%%')
                    ORDER BY rank DESC
                    LIMIT 24
                ), raw_location_candidates AS MATERIALIZED (
                    SELECT business.osm_type, business.osm_id, place.rank
                    FROM matching_places AS place
                    JOIN leadroom_osm_businesses AS business
                      ON ST_Covers(place.geom, business.geom)
                    UNION ALL
                    SELECT business.osm_type, business.osm_id,
                           greatest(similarity(business.location_text, %(location)s),
                                    word_similarity(%(location)s, business.location_text)) AS rank
                    FROM leadroom_osm_businesses AS business
                    WHERE %(location)s <> ''
                      AND NOT EXISTS (SELECT 1 FROM matching_places)
                      AND (%(location)s <%% business.location_text
                           OR business.location_text ILIKE '%%' || %(location)s || '%%')
                    UNION ALL
                    SELECT business.osm_type, business.osm_id, 0::real AS rank
                    FROM leadroom_osm_businesses AS business
                    WHERE %(location)s = ''
                ), location_candidates AS MATERIALIZED (
                    SELECT osm_type, osm_id, max(rank) AS rank
                    FROM raw_location_candidates
                    GROUP BY osm_type, osm_id
                )
                SELECT business.osm_type, business.osm_id, business.name, business.category,
                       business.category_value, business.website, business.phone, business.email,
                       business.address, business.city, business.postcode,
                       ST_Y(business.geom) AS latitude, ST_X(business.geom) AS longitude,
                       greatest({niche_rank}) AS niche_rank,
                       location_match.rank AS location_rank
                FROM leadroom_osm_businesses AS business
                JOIN location_candidates AS location_match
                  ON location_match.osm_type = business.osm_type
                 AND location_match.osm_id = business.osm_id
                WHERE ({niche_match})
                ORDER BY location_rank DESC, niche_rank DESC,
                         (website <> '') DESC, (email <> '') DESC, (phone <> '') DESC, name
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                {
                    **niche_parameters,
                    "location": location_term,
                    "limit": limit,
                    "offset": offset,
                },
            )
            rows = cursor.fetchall()
        return [self._candidate(row) for row in rows]

    def preview(self, niche: str, location: str, limit: int = 8) -> dict[str, Any]:
        started = time.perf_counter()
        results = self.search(niche, location, limit)
        return {
            "count": len(results),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "results": results,
        }

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=3)

    @property
    def _use_wsl_bridge(self) -> bool:
        return sys.platform == "win32" and "OSM_DATABASE_URL" not in os.environ

    def _wsl_status(self, result: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            engine = self._wsl_json(
                "SELECT json_build_object('version', PostGIS_Version(), "
                "'table_ready', to_regclass('public.leadroom_osm_businesses') IS NOT NULL)"
            )
            if not engine["table_ready"]:
                result.update(
                    database="online",
                    postgis_version=engine["version"],
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    message="Engine ready. Import an OSM dataset to begin local discovery.",
                )
                return result
            counts = self._wsl_json(
                "SELECT json_build_object("
                "'businesses', count(*), "
                "'with_website', count(*) FILTER (WHERE website <> ''), "
                "'with_phone', count(*) FILTER (WHERE phone <> ''), "
                "'with_email', count(*) FILTER (WHERE email <> '')) "
                "FROM leadroom_osm_businesses"
            )
            imported = self._wsl_json(
                "SELECT json_build_object("
                "'last_imported_at', max(value) FILTER (WHERE key = 'last_imported_at'), "
                "'last_updated_at', max(value) FILTER (WHERE key = 'last_updated_at'), "
                "'update_status', coalesce(max(value) FILTER (WHERE key = 'update_status'), "
                "'not_configured'), "
                "'update_message', coalesce(max(value) FILTER (WHERE key = 'update_message'), "
                "'Automatic updates are not configured.')) "
                "FROM leadroom_osm_metadata"
            )
            result.update(
                ready=counts["businesses"] > 0,
                database="online",
                postgis_version=engine["version"],
                latency_ms=round((time.perf_counter() - started) * 1000),
                **imported,
                message="Local discovery is ready." if counts["businesses"] else "Dataset is empty.",
                **counts,
            )
            return result
        except Exception as exc:
            result["message"] = str(exc).splitlines()[0][:240]
            return result

    def _wsl_search(
        self, niche_terms: list[str], location: str, limit: int, offset: int
    ) -> list[dict[str, str]]:
        niche_sql = [_sql_literal(term) for term in niche_terms]
        location_sql = _sql_literal(location)
        niche_rank = ", ".join(
            part
            for term in niche_sql
            for part in (
                f"similarity(business.search_text, {term})",
                f"word_similarity({term}, business.search_text)",
            )
        )
        niche_match = " OR ".join(
            f"{term} <% business.search_text OR business.search_text ILIKE '%' || {term} || '%'"
            for term in niche_sql
        )
        query = f"""
            WITH matching_places AS MATERIALIZED (
                SELECT place.geom,
                       greatest(similarity(place.search_text, {location_sql}),
                                word_similarity({location_sql}, place.search_text)) AS rank
                FROM leadroom_osm_places AS place
                WHERE {location_sql} <> ''
                  AND ST_Dimension(place.geom) >= 2
                  AND ({location_sql} <% place.search_text
                       OR place.search_text ILIKE '%' || {location_sql} || '%')
                ORDER BY rank DESC
                LIMIT 24
            ), raw_location_candidates AS MATERIALIZED (
                SELECT business.osm_type, business.osm_id, place.rank
                FROM matching_places AS place
                JOIN leadroom_osm_businesses AS business
                  ON ST_Covers(place.geom, business.geom)
                UNION ALL
                SELECT business.osm_type, business.osm_id,
                       greatest(similarity(business.location_text, {location_sql}),
                                word_similarity({location_sql}, business.location_text)) AS rank
                FROM leadroom_osm_businesses AS business
                WHERE {location_sql} <> ''
                  AND NOT EXISTS (SELECT 1 FROM matching_places)
                  AND ({location_sql} <% business.location_text
                       OR business.location_text ILIKE '%' || {location_sql} || '%')
                UNION ALL
                SELECT business.osm_type, business.osm_id, 0::real AS rank
                FROM leadroom_osm_businesses AS business
                WHERE {location_sql} = ''
            ), location_candidates AS MATERIALIZED (
                SELECT osm_type, osm_id, max(rank) AS rank
                FROM raw_location_candidates
                GROUP BY osm_type, osm_id
            )
            SELECT coalesce(json_agg(row_to_json(candidate)), '[]'::json)
            FROM (
                SELECT business.osm_type, business.osm_id, business.name, business.category,
                       business.category_value, business.website, business.phone, business.email,
                       business.address, business.city, business.postcode,
                       ST_Y(business.geom) AS latitude, ST_X(business.geom) AS longitude,
                       greatest({niche_rank}) AS niche_rank,
                       location_match.rank AS location_rank
                FROM leadroom_osm_businesses AS business
                JOIN location_candidates AS location_match
                  ON location_match.osm_type = business.osm_type
                 AND location_match.osm_id = business.osm_id
                WHERE ({niche_match})
                ORDER BY location_rank DESC, niche_rank DESC,
                         (website <> '') DESC, (email <> '') DESC, (phone <> '') DESC, name
                LIMIT {int(limit)} OFFSET {int(offset)}
            ) AS candidate
        """
        return [self._candidate(row) for row in self._wsl_json(query)]

    @staticmethod
    def _wsl_json(query: str) -> Any:
        completed = _run_hidden(
            [
                "wsl",
                "-d",
                "Ubuntu",
                "-u",
                "postgres",
                "--",
                "psql",
                "-d",
                "leadroom_osm",
                "-Atq",
                "-c",
                query,
            ],
            timeout=20,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "WSL PostgreSQL query failed")
        return json.loads(completed.stdout.strip() or "null")

    def request_update(self) -> dict[str, str]:
        if not self._use_wsl_bridge:
            raise RuntimeError("Manual sync is only available from the Windows local engine")
        completed = _run_hidden(
            [
                "wsl",
                "-d",
                "Ubuntu",
                "-u",
                "root",
                "--",
                "systemctl",
                "start",
                "--no-block",
                "leadroom-osm-update.service",
            ],
            timeout=8,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "Could not start the local data update")
        return {"status": "started", "message": "Local data sync started in the background."}

    @staticmethod
    def _candidate(row: dict[str, Any]) -> dict[str, str]:
        website = str(row.get("website") or "").strip()
        osm_type = str(row["osm_type"])
        osm_path_type = {"N": "node", "W": "way", "R": "relation"}.get(osm_type, osm_type)
        osm_id = str(row["osm_id"])
        identity = f"osm-{osm_type}-{osm_id}"
        category = " ".join(
            part.replace("_", " ")
            for part in [str(row.get("category") or ""), str(row.get("category_value") or "")]
            if part
        )
        area = ", ".join(
            part for part in [str(row.get("city") or ""), str(row.get("postcode") or "")] if part
        )
        return {
            "source": "osm_local",
            "sources": ["local"],
            "source_id": identity,
            "title": str(row.get("name") or identity),
            "url": website,
            "homepage": website,
            "snippet": " | ".join(part for part in [category, str(row.get("address") or ""), area] if part),
            "domain": domain_key(website) or identity,
            "business_name": str(row.get("name") or ""),
            "business_type": category,
            "city_or_area": area,
            "address": str(row.get("address") or ""),
            "phone": str(row.get("phone") or ""),
            "email": str(row.get("email") or ""),
            "latitude": str(row.get("latitude") or ""),
            "longitude": str(row.get("longitude") or ""),
            "osm_url": f"https://www.openstreetmap.org/{osm_path_type}/{osm_id}",
        }


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_hidden(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    options: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
    }
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        options.update(
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            startupinfo=startupinfo,
        )
    return subprocess.run(command, **options)


def _expand_niche(value: str) -> list[str]:
    normalized = " ".join(value.casefold().split())
    meaningful = " ".join(token for token in normalized.split() if token not in NICHE_QUALIFIERS)
    terms = [meaningful or normalized]
    for trigger, aliases in NICHE_ALIASES.items():
        if trigger in normalized:
            terms.extend(aliases)
    return list(dict.fromkeys(term for term in terms if term))
