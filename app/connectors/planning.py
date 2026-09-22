import httpx

ENTITY_BASE = "https://www.planning.data.gov.uk/entity.json"

CONSTRAINT_DATASETS = [
    "listed-building",
    "conservation-area",
    "article-4-direction-area",
    "green-belt",
    "tree-preservation-zone",
]

async def _entity_query(lat: float | None = None, lon: float | None = None, datasets: list[str] | None = None, uprn: str | None = None, limit: int = 100) -> list[dict]:
    params: list[tuple[str, str]] = [("limit", str(limit))]
    if uprn:
        params.append(("q", str(uprn)))
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

async def _safe_query(lat: float, lon: float, datasets: list[str], uprn: str | None = None, limit: int = 100) -> list[dict]:
    try:
        result = await _entity_query(lat=lat, lon=lon, uprn=uprn, datasets=datasets, limit=limit)
        # A UPRN text query can legitimately return no result where dataset coverage
        # is incomplete. In that case retain the coordinate lookup as evidence too.
        if uprn and not result:
            return await _entity_query(lat=lat, lon=lon, datasets=datasets, limit=limit)
        return result
    except Exception:
        if uprn:
            try:
                return await _entity_query(lat=lat, lon=lon, datasets=datasets, limit=limit)
            except Exception:
                pass
        return []

async def constraints(lat: float, lon: float, uprn: str | None = None) -> list[dict]:
    return await _safe_query(lat, lon, CONSTRAINT_DATASETS, uprn=uprn)

async def listed_buildings(lat: float, lon: float, uprn: str | None = None) -> list[dict]:
    return await _safe_query(lat, lon, ["listed-building"], uprn=uprn, limit=25)

async def planning_history(lat: float, lon: float, uprn: str | None = None) -> list[dict]:
    return await _safe_query(lat, lon, ["planning-application"], uprn=uprn, limit=100)
