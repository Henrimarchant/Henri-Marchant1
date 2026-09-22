import httpx

ENTITY_BASE = "https://www.planning.data.gov.uk/entity.json"

CONSTRAINT_DATASETS = [
    "listed-building",
    "conservation-area",
    "article-4-direction-area",
    "green-belt",
    "tree-preservation-zone",
]

async def _entity_query(lat: float, lon: float, datasets: list[str], limit: int = 100) -> list[dict]:
    params: list[tuple[str, str]] = [
        ("latitude", str(lat)), ("longitude", str(lon)), ("limit", str(limit)),
    ]
    params.extend(("dataset", d) for d in datasets)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(ENTITY_BASE, params=params)
        r.raise_for_status()
        return r.json().get("entities", [])

async def constraints(lat: float, lon: float) -> list[dict]:
    return await _entity_query(lat, lon, CONSTRAINT_DATASETS)

async def planning_history(lat: float, lon: float) -> list[dict]:
    # Planning application coverage is not uniform nationally. Returned records
    # are evidence; an empty response must never be presented as "no history".
    try:
        return await _entity_query(lat, lon, ["planning-application"], limit=100)
    except httpx.HTTPStatusError:
        return []
