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
    lat: float,
    lon: float,
    datasets: list[str],
    limit: int = 100,
) -> list[dict]:

    params: list[tuple[str, str]] = [
        ("latitude", str(lat)),
        ("longitude", str(lon)),
        ("limit", str(limit)),
    ]

    params.extend(("dataset", d) for d in datasets)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(ENTITY_BASE, params=params)
        r.raise_for_status()
        return r.json().get("entities", [])


async def constraints(lat: float, lon: float) -> list[dict]:
    # Planning constraints are optional enrichment.
    # Failure must never prevent the Building Record from being created.
    try:
        return await _entity_query(
            lat,
            lon,
            CONSTRAINT_DATASETS,
        )
    except Exception:
        return []


async def planning_history(lat: float, lon: float) -> list[dict]:
    # Planning application coverage is not uniform nationally.
    # An unavailable source or empty response must not be treated
    # as proof that the building has no planning history.
    try:
        return await _entity_query(
            lat,
            lon,
            ["planning-application"],
            limit=100,
        )
    except Exception:
        return []
