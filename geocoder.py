import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"

async def geocode(address: str) -> dict:
    # Prototype-only geocoder. Production must use a source whose usage/licence
    # is appropriate for the intended scale and product.
    headers = {"User-Agent": "BuildingRecordV0/0.1 (prototype)"}
    params = {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(NOMINATIM, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
    if not data:
        raise ValueError("Address not found")
    x = data[0]
    return {
        "display_name": x["display_name"],
        "lat": float(x["lat"]),
        "lon": float(x["lon"]),
        "osm_type": x.get("osm_type"),
        "osm_id": x.get("osm_id"),
    }
