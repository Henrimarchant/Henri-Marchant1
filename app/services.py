import hashlib
import math

from .models import BuildingIdentity, BuildingRecord, EvidenceStatus, Event, Fact, Source
from .connectors.planning import constraints as get_constraints, listed_building_match, planning_history
from .connectors.overture import resolve_building
from .roof import build_roof

def stable_record_id(lat: float, lon: float, uprn: str | None = None) -> str:
    raw = (f"uprn:{uprn}" if uprn else f"{lat:.7f},{lon:.7f}").encode()
    return "br_" + hashlib.sha256(raw).hexdigest()[:16]

def present(value):
    return value is not None and not (isinstance(value, float) and math.isnan(value))

def planning_source(dataset: str, entity: dict) -> Source:
    return Source(
        provider="Planning Data / Historic England" if dataset == "listed-building" else "Planning Data",
        dataset=dataset,
        reference=str(entity.get("reference") or entity.get("entity") or ""),
        licence_note="Open Government Licence. Coverage and spatial matching vary by dataset; an empty result is not proof of absence.",
    )

async def build_record(address: str, lat: float, lon: float, uprn: str | None = None,
                       uprn_status: EvidenceStatus = EvidenceStatus.unknown,
                       uprn_confidence: float | None = None, uprn_source: Source | None = None) -> BuildingRecord:
    overture = await resolve_building(lat, lon)
    identity = BuildingIdentity(
        record_id=stable_record_id(lat, lon, uprn if uprn_status == EvidenceStatus.verified else None), address=address, latitude=lat, longitude=lon,
        uprn=uprn if uprn_status == EvidenceStatus.verified else None, gers_id=(overture or {}).get("gers_id"),
        uprn_status=uprn_status if uprn_status == EvidenceStatus.verified else EvidenceStatus.unknown,
        uprn_confidence=uprn_confidence if uprn_status == EvidenceStatus.verified else None,
        uprn_source=uprn_source if uprn_status == EvidenceStatus.verified else None,
    )
    geo_source = Source(provider="OpenStreetMap / Nominatim", dataset="address-resolution",
                        licence_note="Location candidate validated against the submitted address; this is not an authoritative UPRN match.")
    facts = [
        Fact(attribute="latitude", value=lat, status=EvidenceStatus.recorded, confidence=0.9, source=geo_source,
             note="Validated geocoder coordinate; property identity is not yet UPRN-verified."),
        Fact(attribute="longitude", value=lon, status=EvidenceStatus.recorded, confidence=0.9, source=geo_source,
             note="Validated geocoder coordinate; property identity is not yet UPRN-verified."),
    ]
    # Never promote a caller-supplied identifier into evidence unless it has
    # actually been verified by a trusted resolver.
    verified_uprn = uprn if uprn and uprn_status == EvidenceStatus.verified else None
    if verified_uprn:
        facts.append(Fact(attribute="UPRN", value=verified_uprn, status=EvidenceStatus.verified,
                          confidence=uprn_confidence, source=uprn_source,
                          note="Unique Property Reference Number verified for this record."))

    if overture:
        osrc = Source(provider="Overture Maps Foundation", dataset="buildings", reference=overture.get("gers_id"))
        for label, key, unit in [
            ("building subtype","subtype",None),("building class","class",None),("height","height","m"),
            ("above-ground floors","num_floors",None),("roof material","roof_material",None),
            ("roof shape","roof_shape",None),("roof ridge direction","roof_direction","degrees"),
        ]:
            value=overture.get(key)
            if present(value):
                facts.append(Fact(attribute=label,value=value,unit=unit,status=EvidenceStatus.recorded,source=osrc))

    constraint_facts = []
    constraint_entities = await get_constraints(lat, lon, uprn=verified_uprn)
    listing = next(
        (e for e in constraint_entities if e.get("dataset") == "listed-building"),
        None,
    )
    if not listing:
        listing = await listed_building_match(address, lat, lon, uprn=verified_uprn)

    # A positive listing match is explicit. A missing match is deliberately
    # "no confirmed match", not "not listed", because spatial/coverage limitations exist.
    if listing:
        lsrc = planning_source("listed-building", listing)
        constraint_facts.extend([
            Fact(attribute="Listed building status", value="Listed", status=EvidenceStatus.recorded, confidence=1.0, source=lsrc),
            Fact(attribute="Listing grade", value=listing.get("listed-building-grade") or "Unknown", status=EvidenceStatus.recorded if listing.get("listed-building-grade") else EvidenceStatus.unknown, confidence=1.0 if listing.get("listed-building-grade") else None, source=lsrc),
            Fact(attribute="List Entry Number", value=listing.get("reference") or listing.get("listed-building"), status=EvidenceStatus.recorded, confidence=1.0, source=lsrc),
            Fact(attribute="Listing name", value=listing.get("name") or "Unknown", status=EvidenceStatus.recorded if listing.get("name") else EvidenceStatus.unknown, confidence=1.0 if listing.get("name") else None, source=lsrc),
            Fact(attribute="First listed", value=listing.get("start-date") or "Unknown", status=EvidenceStatus.recorded if listing.get("start-date") else EvidenceStatus.unknown, source=lsrc),
        ])
    else:
        constraint_facts.append(Fact(
            attribute="Listed building status", value="No confirmed listing match",
            status=EvidenceStatus.unknown,
            note="No matching listed-building record was returned. This is not proof that the building is not listed.",
            source=Source(provider="Planning Data / Historic England", dataset="listed-building",
                          licence_note="National listing data is authoritative, but this prototype's property-to-spatial match is not yet authoritative.")
        ))

    for entity in constraint_entities:
        dataset = entity.get("dataset", "planning-data")
        if dataset == "listed-building":
            continue
        value = entity.get("name") or entity.get("reference") or entity.get("entity")
        constraint_facts.append(Fact(attribute=dataset, value=value, status=EvidenceStatus.recorded,
                                     confidence=1.0, source=planning_source(dataset, entity)))

    history=[]
    for index, entity in enumerate(await planning_history(lat, lon, uprn=verified_uprn)):
        reference=str(entity.get("reference") or entity.get("entity") or index)
        description=entity.get("name") or entity.get("description") or f"Planning record {reference}"
        event_date=entity.get("entry-date") or entity.get("start-date")
        history.append(Event(
            event_id="planning_"+hashlib.sha256(reference.encode()).hexdigest()[:10],
            event_type="planning_record", event_date=event_date, description=str(description),
            source=Source(provider="Planning Data",dataset="planning-application",reference=reference), confidence=1.0
        ))

    roof=build_roof(identity.record_id, facts)
    attrs={f.attribute for f in facts}
    # Evidence gaps are explicit and actionable. They are not claims that the
    # information does not exist, only that this record has not resolved it yet.
    unknowns=[x for x in [
        "UPRN","building footprint","building use/type","construction date",
        "original construction period","number of storeys","building height",
        "gross floor area","external wall construction","window type",
        "window installation date","roof covering","roof form","roof area",
        "roof installation/replacement date","drainage condition",
        "EPC / energy evidence","building alteration chronology"
    ] if x not in attrs]
    return BuildingRecord(identity=identity,facts=facts,constraints=constraint_facts,
                          components=[roof],history=history,unknowns=unknowns)
