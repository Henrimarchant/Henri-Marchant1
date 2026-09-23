import math
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
    stop = {"the","and","of","road","street","lane","close","drive","avenue",
            "england","united","kingdom","uk"}
    return {t for t in re.findall(r"[a-z0-9]+", value.lower()) if len(t)>2 and t not in stop}


def _score(query: str, item: dict, requested_postcode: str | None) -> float:
    candidate_postcode = _candidate_postcode(item)
    if requested_postcode and candidate_postcode != requested_postcode:
        return -100.0
    query_tokens = _tokens(POSTCODE_RE.sub("", query))
    candidate_text = " ".join([str(item.get("display_name") or ""),
        " ".join(str(v) for v in (item.get("address") or {}).values())])
    overlap = len(query_tokens & _tokens(candidate_text))
    name_score = overlap / max(min(len(query_tokens),4),1) if query_tokens else 0.0
    kind_bonus = 0.15 if str(item.get("type") or "") in {"house","building","residential","apartments","yes"} else 0.0
    return name_score + kind_bonus + min(float(item.get("importance") or 0.0),1.0)*0.05


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r=6371000.0
    p1,p2=math.radians(a_lat),math.radians(b_lat)
    dp=math.radians(b_lat-a_lat); dl=math.radians(b_lon-a_lon)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(h))


async def _search(client, headers, **params):
    base={"format":"jsonv2","limit":10,"addressdetails":1,"countrycodes":"gb"}
    base.update(params)
    response=await client.get(NOMINATIM,params=base,headers=headers)
    response.raise_for_status()
    return response.json()


async def geocode(address: str) -> dict:
    """Resolve a property conservatively, using postcode as a spatial anchor."""
    headers={"User-Agent":"BuildingRecordV0/0.6 (prototype)"}
    requested_postcode=_requested_postcode(address)
    query_without_postcode=POSTCODE_RE.sub("",address).strip(" ,")
    if not requested_postcode:
        raise ValueError("Enter the full property address including postcode so the building can be identified safely.")
    if not query_without_postcode:
        raise ValueError("A postcode identifies an area, not a unique property. Enter the full property address.")

    async with httpx.AsyncClient(timeout=15) as client:
        data=await _search(client,headers,q=address)

        # First accept only candidates carrying the requested postcode.
        ranked=sorted(((_score(address,x,requested_postcode),x) for x in data),
                      key=lambda p:p[0],reverse=True)
        valid=[p for p in ranked if p[0]>=0.25]

        # Some named buildings do not carry a postcode in OSM. Anchor a second
        # search tightly around the postcode rather than accepting a same-name
        # building elsewhere in Britain.
        method="exact-postcode-candidate"
        if not valid and requested_postcode:
            pc=await _search(client,headers,q=requested_postcode,limit=3)
            if pc:
                centre=pc[0]; clat=float(centre["lat"]); clon=float(centre["lon"])
                delta=0.03
                local=await _search(client,headers,q=query_without_postcode,
                    viewbox=f"{clon-delta},{clat+delta},{clon+delta},{clat-delta}",bounded=1)
                scored=[]
                for item in local:
                    dist=_distance_m(clat,clon,float(item["lat"]),float(item["lon"]))
                    name_overlap=len(_tokens(query_without_postcode)&_tokens(str(item.get("display_name") or "")))
                    name_score=name_overlap/max(min(len(_tokens(query_without_postcode)),4),1)
                    # postcode centroid is an anchor, not identity: require a
                    # strong name match and a conservative local radius.
                    if dist<=3000 and name_score>=0.5:
                        scored.append((name_score + max(0,1-dist/3000)*0.1,item))
                valid=sorted(scored,key=lambda p:p[0],reverse=True)
                method="postcode-anchored-name-match"

        if not valid:
            raise ValueError("Property identity could not be confirmed reliably from the supplied address.")

        best_score,best=valid[0]
        if len(valid)>1 and best_score-valid[1][0]<0.08 and best.get("display_name")!=valid[1][1].get("display_name"):
            raise ValueError("More than one property matches this search. Add more address detail.")

    return {"display_name":best["display_name"],"lat":float(best["lat"]),"lon":float(best["lon"]),
            "osm_type":best.get("osm_type"),"osm_id":best.get("osm_id"),
            "postcode":_candidate_postcode(best) or requested_postcode,
            "identity_confirmed":True,"identity_method":method}


# Backwards-compatible explicit name used by identity safety tests/callers.
geocode_address = geocode
