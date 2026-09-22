import re

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)


def _normalise_postcode(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", value).upper()


def _requested_postcode(query: str) -> str | None:
    match = POSTCODE_RE.search(query)
    return _normalise_postcode(match.group(1)) if match else None


def _candidate_postcode(item: dict) -> str | None:
    return _normalise_postcode((item.get("address") or {}).get("postcode"))


def _tokens(value: str) -> set[str]:
    stop = {
        "the", "and", "of", "road", "street", "lane", "close", "drive",
        "avenue", "england", "united", "kingdom", "uk",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in stop and not POSTCODE_RE.fullmatch(token)
    }


def _score(query: str, item: dict, requested_postcode: str | None) -> float:
    candidate_postcode = _candidate_postcode(item)
    if requested_postcode and candidate_postcode != requested_postcode:
        return -100.0

    query_tokens = _tokens(POSTCODE_RE.sub("", query))
    candidate_text = " ".join([
        str(item.get("display_name") or ""),
        " ".join(str(v) for v in (item.get("address") or {}).values()),
    ])
    candidate_tokens = _tokens(candidate_text)
    overlap = len(query_tokens & candidate_tokens)
    name_score = overlap / max(min(len(query_tokens), 4), 1) if query_tokens else 0.0

    # Prefer address/building-like candidates over broad administrative places.
    kind = str(item.get("type") or "")
    kind_bonus = 0.15 if kind in {"house", "building", "residential", "apartments", "yes"} else 0.0
    importance = float(item.get("importance") or 0.0)
    return name_score + kind_bonus + min(importance, 1.0) * 0.05


async def geocode(address: str) -> dict:
    """
    Resolve a search to a location without blindly trusting the first result.

    If the user supplies a postcode, candidates with a different postcode are
    rejected. Named-property searches must also have a meaningful textual
    match. If identity is ambiguous, fail closed instead of enriching the
    wrong building.
    """
    headers = {"User-Agent": "BuildingRecordV0/0.5 (prototype)"}
    requested_postcode = _requested_postcode(address)
    params = {
        "q": address,
        "format": "jsonv2",
        "limit": 10,
        "addressdetails": 1,
        "countrycodes": "gb",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(NOMINATIM, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

    if not data:
        raise ValueError("Property could not be identified from that search.")

    ranked = sorted(
        ((_score(address, item, requested_postcode), item) for item in data),
        key=lambda pair: pair[0],
        reverse=True,
    )
    ranked = [pair for pair in ranked if pair[0] > -50]

    if not ranked:
        raise ValueError(
            "Property identity could not be confirmed: returned locations did not match the supplied postcode."
        )

    best_score, best = ranked[0]

    # A postcode-only query can legitimately identify only the postcode area,
    # not a unique property. Keep it usable, but mark it unconfirmed.
    query_without_postcode = POSTCODE_RE.sub("", address).strip(" ,")
    named_search = bool(query_without_postcode)

    if named_search and best_score < 0.25:
        raise ValueError(
            "Property identity could not be confirmed reliably. Add the full property address."
        )

    # If two materially different candidates are essentially tied, do not guess.
    if len(ranked) > 1 and abs(best_score - ranked[1][0]) < 0.03:
        first = best.get("display_name")
        second = ranked[1][1].get("display_name")
        if first != second:
            raise ValueError(
                "More than one property matches this search. Add the full address so the correct building can be confirmed."
            )

    return {
        "display_name": best["display_name"],
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
        "osm_type": best.get("osm_type"),
        "osm_id": best.get("osm_id"),
        "postcode": _candidate_postcode(best),
        "identity_confirmed": named_search and (
            not requested_postcode or _candidate_postcode(best) == requested_postcode
        ),
        "identity_method": "validated-geocoder-candidate",
    }
