"""PostGIS-backed OS Open UPRN lookup.

The web service queries a spatial index; it never scans the national CSV.
Import jobs should load OS Open UPRN into:

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS os_open_uprn (
    uprn bigint PRIMARY KEY,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS os_open_uprn_geom_gix
ON os_open_uprn USING GIST (geom);
"""
import os

_pool = None

try:
    import asyncpg
except ImportError:  # deployment remains usable until DB dependency is installed
    asyncpg = None

DATABASE_URL = os.getenv("UPRN_DATABASE_URL")
MAX_VERIFY_DISTANCE_M = 12.0
AMBIGUITY_MARGIN_M = 4.0


async def _get_pool():
    global _pool
    if not DATABASE_URL or asyncpg is None:
        return None
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, command_timeout=10)
    return _pool


async def nearby_uprns(lat: float, lon: float, limit: int = 2) -> list[dict]:
    pool = await _get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uprn, latitude, longitude,
                   ST_Distance(
                     geom::geography,
                     ST_SetSRID(ST_MakePoint($2,$1),4326)::geography
                   ) AS distance_m
            FROM os_open_uprn
            WHERE ST_DWithin(
              geom::geography,
              ST_SetSRID(ST_MakePoint($2,$1),4326)::geography,
              $3
            )
            ORDER BY distance_m
            LIMIT $4
            """,
            lat, lon, MAX_VERIFY_DISTANCE_M, limit,
        )
        return [dict(row) for row in rows]


async def nearby_uprns_result(lat: float, lon: float, limit: int = 2) -> SourceResult:
    """Query the indexed national UPRN source without hiding infrastructure failure."""
    if not DATABASE_URL:
        return SourceResult(state=SourceState.incomplete, note="UPRN database is not configured.")
    if asyncpg is None:
        return SourceResult(state=SourceState.unavailable, note="UPRN database driver is unavailable.")
    try:
        records=await nearby_uprns(lat,lon,limit)
        return SourceResult(
            state=SourceState.success if records else SourceState.no_match,
            records=records,
            note=None if records else "No OS Open UPRN coordinate was found within the conservative search radius.",
        )
    except Exception:
        return SourceResult(
            state=SourceState.unavailable,
            note="The indexed OS Open UPRN source could not be queried; this is not evidence that no UPRN exists.",
        )


async def close_pool():
    """Close pooled database connections during application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool=None
