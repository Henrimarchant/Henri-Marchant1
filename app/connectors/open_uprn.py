import csv
import math
import os
from functools import lru_cache
from pathlib import Path

from ..models import EvidenceStatus, Source

DATA_PATH = Path(os.getenv("OS_OPEN_UPRN_CSV", "data/os-open-uprn.csv"))
MAX_VERIFY_DISTANCE_M = 12.0
AMBIGUITY_MARGIN_M = 4.0


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(h))


@lru_cache(maxsize=1)
def _load_points() -> list[tuple[str, float, float]]:
    """Load the official OS Open UPRN CSV when supplied to the deployment.

    OS Open UPRN contains identifiers and coordinates, not full postal
    addresses. It is therefore used only to verify a tightly matched location,
    never to invent an address match.
    """
    if not DATA_PATH.exists():
        return []
    points = []
    with DATA_PATH.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                points.append((str(row["UPRN"]), float(row["LATITUDE"]), float(row["LONGITUDE"])))
            except (KeyError, TypeError, ValueError):
                continue
    return points


async def resolve_uprn(lat: float, lon: float) -> dict | None:
    # Production path: query the PostGIS spatial index. The local CSV path
    # remains only as a development fallback.
    try:
        from .uprn_postgis import nearby_uprns
        indexed = await nearby_uprns(lat, lon, 2)
    except Exception:
        indexed = []
    if indexed:
        nearest = [(float(x["distance_m"]), str(x["uprn"]), float(x["latitude"]), float(x["longitude"])) for x in indexed]
    else:
        points = _load_points()
        if not points:
            return None
        nearest = sorted(
            ((_distance_m(lat, lon, plat, plon), uprn, plat, plon) for uprn, plat, plon in points),
            key=lambda item: item[0],
        )[:2]
    if not nearest or nearest[0][0] > MAX_VERIFY_DISTANCE_M:
        return None
    if len(nearest) > 1 and nearest[1][0] - nearest[0][0] < AMBIGUITY_MARGIN_M:
        return None

    distance, uprn, plat, plon = nearest[0]
    return {
        "uprn": uprn,
        "latitude": plat,
        "longitude": plon,
        "distance_m": round(distance, 2),
        "status": EvidenceStatus.recorded,
        "confidence": 0.85,
        "source": Source(
            provider="Ordnance Survey",
            dataset="OS Open UPRN",
            reference=uprn,
            licence_note="OS OpenData under the Open Government Licence; OS Open UPRN coordinate candidate. Coordinate proximity alone does not verify address-to-UPRN identity.",
        ),
    }


async def corroborate_uprn(address: str, candidate: dict | None) -> dict | None:
    """Corroborate a coordinate candidate against an address-linked public source.

    Planning Data supports UPRN/postcode search but coverage is incomplete.
    A positive address-token match can upgrade the candidate; absence cannot.
    """
    if not candidate:
        return None
    import re
    import httpx
    uprn = str(candidate["uprn"])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://www.planning.data.gov.uk/entity.json",
                                 params={"q": uprn, "limit": 50})
            r.raise_for_status()
            entities = r.json().get("entities", [])
    except Exception:
        return candidate

    stop={"the","and","road","street","lane","avenue","close","drive","england","united","kingdom"}
    wanted={x for x in re.findall(r"[a-z0-9]+", address.lower()) if len(x)>2 and x not in stop}
    for entity in entities:
        text=" ".join(str(entity.get(k) or "") for k in ("name","address-text","description","reference")).lower()
        got={x for x in re.findall(r"[a-z0-9]+", text) if len(x)>2 and x not in stop}
        if wanted and len(wanted & got) / min(len(wanted), 4) >= 0.75:
            upgraded=dict(candidate)
            upgraded["status"]=EvidenceStatus.verified
            upgraded["confidence"]=0.98
            upgraded["source"]=Source(
                provider="Ordnance Survey + Planning Data",
                dataset="OS Open UPRN / address-linked corroboration",
                reference=uprn,
                licence_note="UPRN coordinate candidate corroborated against an address-linked Planning Data entity."
            )
            return upgraded
    return candidate
