"""Atomically import the official OS Open UPRN CSV into PostGIS."""
import asyncio
import csv
import os
import sys
import uuid
from datetime import date, datetime, timezone

import asyncpg

BATCH_SIZE = 100_000
MIN_FREE_SPACE_FACTOR = float(os.getenv("UPRN_MIN_FREE_SPACE_FACTOR", "2.2"))
MIN_EXPECTED_ROWS = int(os.getenv("UPRN_MIN_EXPECTED_ROWS", "30000000"))


def release_date_from_env() -> date | None:
    value = os.getenv("UPRN_RELEASE_DATE")
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError("UPRN_RELEASE_DATE must be YYYY-MM-DD") from exc


async def copy_batch(conn, rows):
    await conn.copy_records_to_table(
        "os_open_uprn_next",
        records=rows,
        columns=["uprn", "latitude", "longitude"],
    )


def required_free_bytes(path: str) -> int:\n    """Conservative capacity estimate for staging table + index + swap headroom."""\n    return int(os.path.getsize(path) * MIN_FREE_SPACE_FACTOR)\n\n\nasync def main(path: str):
    source_reference = os.getenv("UPRN_SOURCE_REFERENCE") or os.path.basename(path)
    release_date = release_date_from_env()
    if not os.path.isfile(path):\n        raise RuntimeError(f"UPRN source file not found: {path}")\n    conn = await asyncpg.connect(os.environ["UPRN_DATABASE_URL"])\n    source_bytes = os.path.getsize(path)
    try:
        db_size = await conn.fetchval("SELECT pg_database_size(current_database())")
        headroom = await conn.fetchval("SELECT pg_size_pretty($1::bigint)", required_free_bytes(path))
        print(
            f"preflight: source={source_bytes:,} bytes; database={db_size:,} bytes; "
            f"recommended free headroom={headroom}",
            flush=True,
        )
        if os.getenv("UPRN_IMPORT_CAPACITY_CONFIRMED") != "1":
            raise RuntimeError(
                "National import blocked until storage capacity is explicitly confirmed. "
                "Set UPRN_IMPORT_CAPACITY_CONFIRMED=1 only after verifying the persistent volume "
                f"has at least {required_free_bytes(path):,} bytes of free import headroom."
            )

        await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        await conn.execute("""CREATE TABLE IF NOT EXISTS dataset_versions(
          provider text NOT NULL, dataset text NOT NULL, release_date date,
          retrieved_at timestamptz NOT NULL, source_reference text,
          licence text, row_count bigint NOT NULL)""")
        await conn.execute("DROP TABLE IF EXISTS os_open_uprn_next")
        await conn.execute("""CREATE TABLE os_open_uprn_next(
          uprn bigint PRIMARY KEY,
          latitude double precision NOT NULL CHECK(latitude BETWEEN 49 AND 61),
          longitude double precision NOT NULL CHECK(longitude BETWEEN -9 AND 3),
          geom geometry(Point,4326) GENERATED ALWAYS AS\n            (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)) STORED)""")

        total = 0
        batch = []
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            required = {"UPRN", "LATITUDE", "LONGITUDE"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise RuntimeError("CSV is not an OS Open UPRN supply: required headers are missing")
            for row in reader:
                try:
                    item = (int(row["UPRN"]), float(row["LATITUDE"]), float(row["LONGITUDE"]))
                except (KeyError, ValueError, TypeError):
                    continue
                batch.append(item)
                if len(batch) >= BATCH_SIZE:
                    await copy_batch(conn, batch)
                    total += len(batch)
                    batch = []
                    print(f"loaded {total:,}", flush=True)
            if batch:
                await copy_batch(conn, batch)
                total += len(batch)

        if total < MIN_EXPECTED_ROWS:
            raise RuntimeError(
                f"Import validation failed: {total:,} valid rows; expected at least {MIN_EXPECTED_ROWS:,}"
            )

        index_name = f"os_open_uprn_next_geom_{uuid.uuid4().hex[:10]}_gix"
        await conn.execute(f"CREATE INDEX {index_name} ON os_open_uprn_next USING GIST(geom)")
        await conn.execute("ANALYZE os_open_uprn_next")

        async with conn.transaction():
            await conn.execute("DROP TABLE IF EXISTS os_open_uprn_previous")
            exists = await conn.fetchval("SELECT to_regclass('public.os_open_uprn') IS NOT NULL")
            if exists:
                await conn.execute("ALTER TABLE os_open_uprn RENAME TO os_open_uprn_previous")
            await conn.execute("ALTER TABLE os_open_uprn_next RENAME TO os_open_uprn")
            await conn.execute("""INSERT INTO dataset_versions(
              provider,dataset,release_date,retrieved_at,source_reference,licence,row_count)
              VALUES($1,$2,$3,$4,$5,$6,$7)""",
              "Ordnance Survey", "OS Open UPRN", release_date,
              datetime.now(timezone.utc), source_reference,
              "Open Government Licence", total)
        print(f"complete: {total:,} rows; live table swapped atomically", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Pass the official OS Open UPRN CSV path")
    asyncio.run(main(sys.argv[1]))
