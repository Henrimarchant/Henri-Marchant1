import csv
import math
import os
from functools import lru_cache
from pathlib import Path

from ..models import EvidenceStatus, Source
from ..source_status import SourceResult, SourceState

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


async def resolve_uprn_result(lat: float, lon: float) -> SourceResult:
    """Resolve a spatial UPRN candidate without hiding source failure."""
    from .uprn_postgis import nearby_uprns_result

    indexed_result = await nearby_uprns_result(lat, lon, 2)
    if indexed_result.state == SourceState.success:
        nearest = [
            (float(x["distance_m"]), str(x["uprn"]), float(x["latitude"]), float(x["longitude"]))
            for x in indexed_result.records
        ]
    else:
        points = _load_points()
        if not points:
            return indexed_result
        nearest = sorted(
            ((_distance_m(lat, lon, plat, plon), uprn, plat, plon) for uprn, plat, plon in points),
            key=lambda item: item[0],
        )[:2]

    if not nearest or nearest[0][0] > MAX_VERIFY_DISTANCE_M:
        return SourceResult(
            state=SourceState.no_match,
            note="No UPRN candidate was found within the conservative identity radius.",
        )
    if len(nearest) > 1 and nearest[1][0] - nearest[0][0] < AMBIGUITY_MARGIN_M:
        return SourceResult(
            state=SourceState.incomplete,
            note="Multiple nearby UPRNs are too close to distinguish safely.",
        )

    distance, uprn, plat, plon = nearest[0]
    candidate = {
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
    return SourceResult(state=SourceState.success, records=[candidate])


async def resolve_uprn(lat: float, lon: float) -> dict | None:
    """Compatibility wrapper returning the candidate only."""
    result = await resolve_uprn_result(lat, lon)
    return result.records[0] if result.records else None


async def corroborate_uprn(address: str, candidate: dict | None) -> dict | None:
    """Do not promote spatial candidates to verified identity.

    The address argument is retained for API compatibility. Verification must
    come from a future authoritative address-to-UPRN source, not text matching.
    """
    return candidate
