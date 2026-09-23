"""Stream OS Open UPRN CSV into PostGIS.

Usage:
  UPRN_DATABASE_URL=... python scripts/import_open_uprn.py /path/to/osopenuprn.csv

The importer batches rows and creates a GiST spatial index after loading.
"""
import asyncio
import csv
import os
import sys

import asyncpg

BATCH_SIZE = 10000

DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS os_open_uprn (
  uprn bigint PRIMARY KEY,
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  geom geometry(Point,4326) NOT NULL
);
"""

async def main(path: str):
    url=os.environ["UPRN_DATABASE_URL"]
    conn=await asyncpg.connect(url)
    try:
        await conn.execute(DDL)
        total=0
        batch=[]
        with open(path,newline="",encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    batch.append((int(row["UPRN"]),float(row["LATITUDE"]),float(row["LONGITUDE"])))
                except (KeyError,ValueError,TypeError):
                    continue
                if len(batch)>=BATCH_SIZE:
                    await load(conn,batch); total+=len(batch); batch=[]
                    print(f"loaded {total:,}",flush=True)
            if batch:
                await load(conn,batch); total+=len(batch)
        await conn.execute("CREATE INDEX IF NOT EXISTS os_open_uprn_geom_gix ON os_open_uprn USING GIST (geom)")
        await conn.execute("ANALYZE os_open_uprn")
        print(f"complete: {total:,} rows",flush=True)
    finally:
        await conn.close()

async def load(conn, rows):
    await conn.executemany(
      """INSERT INTO os_open_uprn(uprn,latitude,longitude,geom)
         VALUES($1,$2,$3,ST_SetSRID(ST_MakePoint($3,$2),4326))
         ON CONFLICT (uprn) DO UPDATE SET latitude=EXCLUDED.latitude,
         longitude=EXCLUDED.longitude,geom=EXCLUDED.geom""", rows)

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Pass the OS Open UPRN CSV path")
    asyncio.run(main(sys.argv[1]))
