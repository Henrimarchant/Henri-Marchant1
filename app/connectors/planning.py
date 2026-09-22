import math
import re

import httpx


ENTITY_BASE = "https://www.planning.data.gov.uk/entity.json"

CONSTRAINT_DATASETS = [
    "listed-building",
    "conservation-area",
    "article-4-direction-area",
    "green-belt",
    "tree-preservation-zone",
]


async def _entity_query(
    lat: float | None = None,
    lon: float | None = None,
    datasets: list[str] | None = None,
    uprn: str | None = None,
    limit: int = 100,
    geometry: str | None = None,
    geometry_relation: str | None = None,
) -> list[dict]:
    params: list[tuple[str, str]] = [("limit", str(limit))]

    if uprn:
        params.append(("q", str(uprn)))
    elif geometry:
        params.append(("geometry", geometry))
        if geometry_relation:
            params.append(("geometry_relation", geometry_relation))
    elif lat is not None and lon is not None:
        params.extend([("latitude", str(lat)), ("longitude", str(lon))])
    else:
        return []

    if datasets:
        params.extend(("dataset", dataset) for dataset in datasets)

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(ENTITY_BASE, params=params)
        response.raise_for_status()
        return response.json().get("entities", [])


def _box(lat: float, lon: float, metres: float = 175) -> str:
    lat_delta = metres / 111_320
    lon_delta = metres / (111_320 * max(math.cos(math.radians(lat)), 0.2))
    west, east = lon - lon_delta, lon + lon_delta
    south, north = lat - lat_delta, lat + lat_delta
    return (
        f"POLYGON(({west} {south},{east} {south},{east} {north},"
        f"{west} {north},{west} {south}))"
    )


def _tokens(text: str) -> set[str]:
    stop = {
        "the", "and", "of", "road", "street", "lane", "main", "england",
        "uk", "united", "kingdom", "nottinghamshire", "newark", "trent",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in stop
    }


def _name_score(address: str, entity: dict) -> float:
    wanted = _tokens(address)
    candidate = _tokens(
        " ".join(
            str(entity.get(key) or "")
            for key in ("name", "reference", "description")
        )
    )
    if not wanted or not candidate:
        return 0.0
    overlap = wanted & candidate
    return len(overlap) / min(len(wanted), 3)


async def listed_building_match(
    address: str,
    lat: float,
    lon: float,
    uprn: str | None = None,
) -> dict | None:
    """
    Resolve a listed-building designation conservatively.

    First use the precise Planning Data lookup. If that misses because the
    geocoder returned a postcode/address centroid, inspect a small local area
    and accept only a strong name match. This prevents a nearby listed building
    being silently attached to the wrong property.
    """
    try:
        exact = await _entity_query(
            lat=lat,
            lon=lon,
            uprn=uprn,
            datasets=["listed-building"],
            limit=20,
        )
        current = [e for e in exact if not e.get("end-date")]
        if current:
            return current[0]
    except Exception:
        pass

    try:
        nearby = await _entity_query(
            datasets=["listed-building"],
            geometry=_box(lat, lon),
            geometry_relation="intersects",
            limit=100,
        )
    except Exception:
        return None

    candidates = [e for e in nearby if not e.get("end-date")]
    scored = sorted(
        ((_name_score(address, entity), entity) for entity in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    if scored and scored[0][0] >= 0.5:
        return scored[0][1]
    return None


async def constraints(
    lat: float,
    lon: float,
    uprn: str | None = None,
) -> list[dict]:
    try:
        return await _entity_query(
            lat=lat,
            lon=lon,
            uprn=uprn,
            datasets=CONSTRAINT_DATASETS,
        )
    except Exception:
        if uprn:
            try:
                return await _entity_query(
                    lat=lat,
                    lon=lon,
                    datasets=CONSTRAINT_DATASETS,
                )
            except Exception:
                pass
        return []


async def planning_history(
    lat: float,
    lon: float,
    uprn: str | None = None,
) -> list[dict]:
    try:
        return await _entity_query(
            lat=lat,
            lon=lon,
            uprn=uprn,
            datasets=["planning-application"],
            limit=100,
        )
    except Exception:
        if uprn:
            try:
                return await _entity_query(
                    lat=lat,
                    lon=lon,
                    datasets=["planning-application"],
                    limit=100,
                )
            except Exception:
                pass
        return []
