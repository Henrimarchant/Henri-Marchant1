"""Atomically import OS Open UPRN CSV into PostGIS.

Loads a staging table with PostgreSQL COPY, validates it, builds the spatial
index, then swaps it into production. A failed import leaves the live table
untouched.
"""
import asyncio
import csv
import os
import sys
from datetime import datetime, timezone

import asyncpg

BATCH_SIZE = 100000

async def main(path: str):
    conn=await asyncpg.connect(os.environ["UPRN_DATABASE_URL"])
    try:
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
          geom geometry(Point,4326))""")

        total=0
        batch=[]
        with open(path,newline="",encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                try:
                    item=(int(row["UPRN"]),float(row["LATITUDE"]),float(row["LONGITUDE"]))
                except (KeyError,ValueError,TypeError):
                    continue
                batch.append(item)
                if len(batch)>=BATCH_SIZE:
                    await copy_batch(conn,batch); total+=len(batch); batch=[]
                    print(f"loaded {total:,}",flush=True)
            if batch:
                await copy_batch(conn,batch); total+=len(batch)

        if total < 1_000_000:
            raise RuntimeError(f"Import validation failed: only {total:,} valid rows")
        await conn.execute("""UPDATE os_open_uprn_next
          SET geom=ST_SetSRID(ST_MakePoint(longitude,latitude),4326)""")
        nulls=await conn.fetchval("SELECT count(*) FROM os_open_uprn_next WHERE geom IS NULL")
        if nulls:
            raise RuntimeError(f"Import validation failed: {nulls} null geometries")
        await conn.execute("ALTER TABLE os_open_uprn_next ALTER COLUMN geom SET NOT NULL")
        await conn.execute("CREATE INDEX os_open_uprn_next_geom_gix ON os_open_uprn_next USING GIST(geom)")
        await conn.execute("ANALYZE os_open_uprn_next")

        async with conn.transaction():
            await conn.execute("DROP TABLE IF EXISTS os_open_uprn_previous")
            exists=await conn.fetchval("SELECT to_regclass('public.os_open_uprn') IS NOT NULL")
            if exists:
                await conn.execute("ALTER TABLE os_open_uprn RENAME TO os_open_uprn_previous")
            await conn.execute("ALTER TABLE os_open_uprn_next RENAME TO os_open_uprn")
            await conn.execute("""INSERT INTO dataset_versions(provider,dataset,retrieved_at,source_reference,licence,row_count)
              VALUES($1,$2,$3,$4,$5,$6)""","Ordnance Survey","OS Open UPRN",
              datetime.now(timezone.utc),os.path.basename(path),"Open Government Licence",total)
        print(f"complete: {total:,} rows; live table swapped atomically",flush=True)
    finally:
        await conn.close()

async def copy_batch(conn,rows):
    await conn.copy_records_to_table("os_open_uprn_next",
        records=rows,columns=["uprn","latitude","longitude"])

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Pass the OS Open UPRN CSV path")
    asyncio.run(main(sys.argv[1]))
