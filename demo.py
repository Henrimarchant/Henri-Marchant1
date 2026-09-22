from .models import (
    BuildingIdentity, BuildingRecord, Fact, Source, EvidenceStatus, Component, Event
)

def demo_record() -> BuildingRecord:
    src = Source(
        provider="Building Record",
        dataset="V0.4 demonstration fixture",
        reference="DEMO-001",
        licence_note="Synthetic demonstration data — not a real property."
    )
    identity = BuildingIdentity(
        record_id="br_demo_0001",
        address="Demonstration Building, England",
        latitude=53.0,
        longitude=-1.5,
        gers_id=None,
    )
    facts = [
        Fact(attribute="building type", value="Residential apartment building",
             status=EvidenceStatus.recorded, confidence=1.0, source=src),
        Fact(attribute="above-ground floors", value=3,
             status=EvidenceStatus.recorded, confidence=1.0, source=src),
    ]
    roof = Component(
        component_id="roof_demo_primary",
        component_type="roof",
        facts=[
            Fact(attribute="form", value="Pitched", status=EvidenceStatus.recorded,
                 confidence=1.0, source=src),
            Fact(attribute="covering", value="Unknown", status=EvidenceStatus.unknown),
            Fact(attribute="installation date", status=EvidenceStatus.unknown),
            Fact(attribute="replacement date", status=EvidenceStatus.unknown),
            Fact(attribute="condition", status=EvidenceStatus.unknown),
            Fact(attribute="last professional inspection", status=EvidenceStatus.unknown),
            Fact(attribute="repair history", status=EvidenceStatus.unknown),
            Fact(attribute="remaining service life", status=EvidenceStatus.unknown),
        ],
    )
    history = [
        Event(event_id="demo_event_1", event_type="record_created",
              event_date="2026-09-22",
              description="Demonstration Building Record created.",
              source=src, confidence=1.0)
    ]
    return BuildingRecord(
        identity=identity, facts=facts, constraints=[],
        components=[roof], history=history,
        unknowns=["construction date", "building alteration chronology",
                  "window installation date", "drainage condition"],
    )
