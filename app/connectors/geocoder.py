import math
import re

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
PLANNING_ENTITY = "https://www.planning.data.gov.uk/entity.json"
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
    if requested_postcode and candidate_postcode and candidate_postcode != requested_postcode:
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


async def _planning_named_building(client, identity_text: str, clat: float, clon: float) -> dict | None:
    """Authoritative fallback for named listed buildings missing from OSM."""
    metres=6000
    lat_delta=metres/111320
    lon_delta=metres/(111320*max(math.cos(math.radians(clat)),0.2))
    west,east=clon-lon_delta,clon+lon_delta
    south,north=clat-lat_delta,clat+lat_delta
    geometry=f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    try:
        r=await client.get(PLANNING_ENTITY,params=[
            ("dataset","listed-building"),("geometry",geometry),
            ("geometry_relation","intersects"),("limit","100")])
        r.raise_for_status()
        entities=[e for e in r.json().get("entities",[]) if not e.get("end-date")]
    except Exception:
        return None
    wanted=_tokens(identity_text)
    ranked=[]
    for e in entities:
        candidate=_tokens(str(e.get("name") or ""))
        score=len(wanted & candidate)/max(len(wanted),1) if wanted else 0
        point=str(e.get("point") or "")
        m=re.search(r"POINT\\s*\\(\\s*(-?[0-9.]+)\\s+(-?[0-9.]+)\\s*\\)",point,re.I)
        if score>=0.8 and m:
            lon,lat=float(m.group(1)),float(m.group(2))
            if _distance_m(clat,clon,lat,lon)<=metres:
                ranked.append((score,e,lat,lon))
    ranked.sort(key=lambda x:x[0],reverse=True)
    if not ranked or (len(ranked)>1 and ranked[0][0]-ranked[1][0]<0.2):
        return None
    score,e,lat,lon=ranked[0]
    return {"display_name": e.get("name") or identity_text, "lat":lat, "lon":lon,
            "osm_type":None,"osm_id":None,"postcode":None,
            "identity_confirmed":True,"identity_method":"authoritative-listed-building-name-match"}


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
        valid=[p for p in ranked if p[0]>=0.25 and (_candidate_postcode(p[1]) == requested_postcode)]

        # Some named buildings do not carry a postcode in OSM. Anchor a second
        # search tightly around the postcode rather than accepting a same-name
        # building elsewhere in Britain.
        method="exact-postcode-candidate"
        if not valid and requested_postcode:
            # Nominatim structured search requires at least one of its address
            # fields; postalcode is valid but some deployments behave better
            # when country is explicit.
            pc=await _search(client,headers,postalcode=requested_postcode,limit=3)
            if not pc:
                pc=await _search(client,headers,q=requested_postcode,limit=3)
            if pc:
                centre=pc[0]; clat=float(centre["lat"]); clon=float(centre["lon"])
                delta=0.06
                # Try progressively simpler property-name variants. Nominatim can
                # miss a named building when the full street/locality string is
                # supplied as an unstructured q value.
                variants=[]
                parts=[p.strip() for p in query_without_postcode.split(",") if p.strip()]
                for q in [query_without_postcode, parts[0] if parts else "", ", ".join(parts[:2]) if len(parts)>1 else ""]:
                    if q and q not in variants:
                        variants.append(q)
                local=[]
                seen=set()
                for q in variants:
                    results=await _search(client,headers,q=q,
                        viewbox=f"{clon-delta},{clat+delta},{clon+delta},{clat-delta}",bounded=1)
                    for item in results:
                        key=(item.get("osm_type"),item.get("osm_id"),item.get("place_id"))
                        if key not in seen:
                            seen.add(key); local.append(item)
                scored=[]
                for item in local:
                    dist=_distance_m(clat,clon,float(item["lat"]),float(item["lon"]))
                    # Identity name matching should be based on the property
                    # name/number, not locality words from the full address.
                    identity_text=parts[0] if parts else query_without_postcode
                    name_overlap=len(_tokens(identity_text)&_tokens(str(item.get("display_name") or "")))
                    name_score=name_overlap/max(len(_tokens(identity_text)),1)
                    # postcode centroid is an anchor, not identity: require a
                    # strong name match and a conservative local radius.
                    if dist<=6000 and name_score>=0.5:
                        scored.append((name_score + max(0,1-dist/6000)*0.1,item))
                valid=sorted(scored,key=lambda p:p[0],reverse=True)
                method="postcode-anchored-name-match"
                if not valid:
                    identity_text=parts[0] if parts else query_without_postcode
                    authoritative=await _planning_named_building(client,identity_text,clat,clon)
                    if authoritative:
                        authoritative["postcode"]=requested_postcode
                        return authoritative

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
