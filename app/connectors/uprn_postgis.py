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

try:
    import asyncpg
except ImportError:  # deployment remains usable until DB dependency is installed
    asyncpg = None

DATABASE_URL = os.getenv("UPRN_DATABASE_URL")
MAX_VERIFY_DISTANCE_M = 12.0
AMBIGUITY_MARGIN_M = 4.0


async def nearby_uprns(lat: float, lon: float, limit: int = 2) -> list[dict]:
    if not DATABASE_URL or asyncpg is None:
        return []
    conn = await asyncpg.connect(DATABASE_URL)
    try:
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
    finally:
        await conn.close()
