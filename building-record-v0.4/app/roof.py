import hashlib
from .models import Component, Fact, Source, EvidenceStatus

def roof_component_id(building_id: str) -> str:
    token = hashlib.sha256(f"{building_id}:roof:primary".encode()).hexdigest()[:10]
    return f"roof_{token}"

def build_roof(building_id: str, building_facts: list[Fact]) -> Component:
    by_attr = {f.attribute: f for f in building_facts}
    roof = Component(component_id=roof_component_id(building_id), component_type="roof")
    mapping = [
        ("roof material", "covering"),
        ("roof shape", "form"),
        ("roof ridge direction", "ridge direction"),
    ]
    for source_attr, roof_attr in mapping:
        if source_attr in by_attr:
            src = by_attr[source_attr]
            roof.facts.append(Fact(
                attribute=roof_attr, value=src.value, unit=src.unit,
                status=src.status, confidence=src.confidence,
                evidence_date=src.evidence_date, source=src.source,
                note="Inherited from building-level remote/public evidence."
            ))

    # These are intentionally explicit Unknowns until supported by evidence.
    existing = {f.attribute for f in roof.facts}
    for attr in ["installation date", "replacement date", "condition",
                 "last professional inspection", "repair history",
                 "remaining service life"]:
        if attr not in existing:
            roof.facts.append(Fact(attribute=attr, status=EvidenceStatus.unknown))
    return roof
