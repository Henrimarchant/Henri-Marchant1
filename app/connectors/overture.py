import asyncio
import overturemaps
from shapely import wkb
from shapely.geometry import Point


def _resolve(lat: float, lon: float) -> dict | None:
    # ~100 m search box; deliberately small to minimise transferred data.
    d = 0.001
    bbox = (lon - d, lat - d, lon + d, lat + d)

    table = (
        overturemaps
        .record_batch_reader("building", bbox)
        .read_all()
        .combine_chunks()
    )

    if table.num_rows == 0:
        return None

    df = table.to_pandas()
    point = Point(lon, lat)
    candidates = []

    for _, r in df.iterrows():
        raw = r.get("geometry")

        if raw is None:
            continue

        geom = wkb.loads(bytes(raw))

        # Prefer the footprint containing the address point; otherwise nearest.
        contains = geom.covers(point)
        distance = geom.distance(point)

        candidates.append(
            (0 if contains else 1, distance, r, geom)
        )

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]))
    _, distance, r, geom = candidates[0]

    # Avoid attaching a clearly unrelated neighbouring building.
    if distance > 0.00035:
        return None

    source = None
    sources = r.get("sources")

    if sources is not None:
        try:
            source = sources[0] if len(sources) else None
        except Exception:
            source = None

    return {
        "gers_id": str(r.get("id")) if r.get("id") else None,
        "subtype": r.get("subtype"),
        "class": r.get("class"),
        "height": r.get("height"),
        "num_floors": r.get("num_floors"),
        "roof_material": r.get("roof_material"),
        "roof_shape": r.get("roof_shape"),
        "roof_direction": r.get("roof_direction"),
        "footprint_area_degrees": geom.area,
        "source": source,
    }


async def resolve_building(lat: float, lon: float) -> dict | None:
    # Overture is optional enrichment.
    # Failure must never prevent the Building Record from being created.
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_resolve, lat, lon),
            timeout=12,
        )
    except Exception:
        return None
