import hashlib, math
from .models import BuildingIdentity, BuildingRecord, Fact, Source, EvidenceStatus, Event
from .connectors.planning import constraints as get_constraints, planning_history
from .connectors.overture import resolve_building
from .roof import build_roof

def stable_record_id(lat: float, lon: float) -> str:
    raw = f"{lat:.7f},{lon:.7f}".encode()
    return "br_" + hashlib.sha256(raw).hexdigest()[:16]

def present(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))

async def build_record(address: str, lat: float, lon: float) -> BuildingRecord:
    overture = await resolve_building(lat, lon)
    identity = BuildingIdentity(
        record_id=stable_record_id(lat, lon), address=address,
        latitude=lat, longitude=lon, gers_id=(overture or {}).get("gers_id"),
    )

    geo_source = Source(provider="Geocoder", dataset="address-resolution")
    facts = [
        Fact(attribute="latitude", value=lat, status=EvidenceStatus.recorded, confidence=1.0, source=geo_source),
        Fact(attribute="longitude", value=lon, status=EvidenceStatus.recorded, confidence=1.0, source=geo_source),
    ]
    if overture:
        osrc = Source(provider="Overture Maps Foundation", dataset="buildings",
                      reference=overture.get("gers_id"))
        for label,key,unit in [
            ("building subtype","subtype",None), ("building class","class",None),
            ("height","height","m"), ("above-ground floors","num_floors",None),
            ("roof material","roof_material",None), ("roof shape","roof_shape",None),
            ("roof ridge direction","roof_direction","degrees"),
        ]:
            v=overture.get(key)
            if present(v):
                facts.append(Fact(attribute=label,value=v,unit=unit,
                                  status=EvidenceStatus.recorded,source=osrc))

    constraint_facts=[]
    for entity in await get_constraints(lat, lon):
        dataset=entity.get("dataset","planning-data")
        value=entity.get("name") or entity.get("reference") or entity.get("entity")
        constraint_facts.append(Fact(
            attribute=dataset,value=value,status=EvidenceStatus.recorded,confidence=1.0,
            source=Source(provider="Planning Data",dataset=dataset,
                          reference=str(entity.get("entity","")),
                          licence_note="Coverage varies; absence of a returned record is not proof of absence.")
        ))

    history=[]
    for i, entity in enumerate(await planning_history(lat, lon)):
        ref=str(entity.get("reference") or entity.get("entity") or i)
        desc=entity.get("name") or entity.get("description") or f"Planning record {ref}"
        date=entity.get("entry-date") or entity.get("start-date")
        history.append(Event(
            event_id="planning_"+hashlib.sha256(ref.encode()).hexdigest()[:10],
            event_type="planning_record", event_date=date, description=str(desc),
            source=Source(provider="Planning Data",dataset="planning-application",reference=ref),
            confidence=1.0
        ))

    roof=build_roof(identity.record_id, facts)
    attrs={f.attribute for f in facts}
    unknowns=[x for x in [
        "construction date","original construction period","building alteration chronology",
        "window installation date","drainage condition"
    ] if x not in attrs]

    return BuildingRecord(identity=identity,facts=facts,constraints=constraint_facts,
                          components=[roof],history=history,unknowns=unknowns)
