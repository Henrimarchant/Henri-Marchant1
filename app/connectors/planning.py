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
) -> list[dict]:
    """
    Query Planning Data.

    Prefer a resolved UPRN when available because it identifies an
    addressable location more precisely than a coordinate-only search.

    Coordinates remain available as the V0 fallback.
    """

    params: list[tuple[str, str]] = [
        ("limit", str(limit)),
    ]

    if uprn:
        params.append(("q", str(uprn)))
    elif lat is not None and lon is not None:
        params.extend(
            [
                ("latitude", str(lat)),
                ("longitude", str(lon)),
            ]
        )
    else:
        return []

    if datasets:
        params.extend(("dataset", dataset) for dataset in datasets)

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            ENTITY_BASE,
            params=params,
        )
        response.raise_for_status()
        return response.json().get("entities", [])


async def constraints(
    lat: float,
    lon: float,
    uprn: str | None = None,
) -> list[dict]:
    """
    Retrieve planning and heritage constraints.

    A failure or empty result must not be interpreted as proof that
    no constraint applies to the property.
    """

    try:
        return await _entity_query(
            lat=lat,
            lon=lon,
            uprn=uprn,
            datasets=CONSTRAINT_DATASETS,
        )
    except Exception:
        # If a UPRN-specific request fails, retain the existing
        # coordinate lookup as a safe fallback.
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
    """
    Retrieve available planning-history evidence.

    Planning application coverage varies geographically. An empty
    response must therefore never be treated as evidence that no
    alterations have taken place.
    """

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
