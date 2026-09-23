CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS os_open_uprn (
  uprn bigint PRIMARY KEY,
  latitude double precision NOT NULL CHECK (latitude BETWEEN 49 AND 61),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -9 AND 3),
  geom geometry(Point,4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS os_open_uprn_geom_gix
ON os_open_uprn USING GIST (geom);
