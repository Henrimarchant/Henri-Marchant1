CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS os_open_uprn (
  uprn bigint PRIMARY KEY,
  latitude double precision NOT NULL CHECK (latitude BETWEEN 49 AND 61),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -9 AND 3),
  geom geometry(Point,4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS os_open_uprn_geom_gix
ON os_open_uprn USING GIST (geom);

CREATE TABLE IF NOT EXISTS dataset_versions (
  provider text NOT NULL,
  dataset text NOT NULL,
  release_date date,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  source_reference text,
  licence text,
  row_count bigint NOT NULL CHECK (row_count >= 0)
);
