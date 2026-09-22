import hashlib
import math

from .models import (
    BuildingIdentity,
    BuildingRecord,
    EvidenceStatus,
    Event,
    Fact,
    Source,
)
from .connectors.planning import (
    constraints as get_constraints,
    planning_history,
)
from .connectors.overture import resolve_building
from .roof import build_roof


def stable_record_id(
    lat: float,
    lon: float,
    uprn: str | None = None,
) -> str:
    """
    Create our persistent Building Record identifier.

    Prefer UPRN once one has been reliably resolved.
    Until then, retain the coordinate-based V0 identity.
    """
    if uprn:
        raw = f"uprn:{uprn}".encode()
    else:
        raw = f"{lat:.7f},{lon:.7f}".encode()

    return "br_" + hashlib.sha256(raw).hexdigest()[:16]


def present(value):
    return value is not None and not (
        isinstance(value, float) and math.isnan(value)
    )


async def build_record(
    address: str,
    lat: float,
    lon: float,
    uprn: str | None = None,
    uprn_status: EvidenceStatus = EvidenceStatus.unknown,
    uprn_confidence: float | None = None,
    uprn_source: Source | None = None,
) -> BuildingRecord:

    # Overture remains optional and is currently disabled in V0.
    overture = await resolve_building(lat, lon)

    identity = BuildingIdentity(
        record_id=stable_record_id(lat, lon, uprn),
        address=address,
        latitude=lat,
        longitude=lon,
        uprn=uprn,
        gers_id=(overture or {}).get("gers_id"),
        uprn_status=uprn_status,
        uprn_confidence=uprn_confidence,
        uprn_source=uprn_source,
    )

    geo_source = Source(
        provider="Geocoder",
        dataset="address-resolution",
        licence_note=(
            "Prototype geocoding source. "
            "Building identity should be strengthened with authoritative identifiers."
        ),
    )

    facts = [
        Fact(
            attribute="latitude",
            value=lat,
            status=EvidenceStatus.recorded,
            confidence=1.0,
            source=geo_source,
        ),
        Fact(
            attribute="longitude",
            value=lon,
            status=EvidenceStatus.recorded,
            confidence=1.0,
            source=geo_source,
        ),
    ]

    # Only expose UPRN as a fact when one has actually been resolved.
    if uprn:
        facts.append(
            Fact(
                attribute="UPRN",
                value=uprn,
                status=uprn_status,
                confidence=uprn_confidence,
                source=uprn_source,
                note=(
                    "Unique Property Reference Number associated with "
                    "this Building Record."
                ),
            )
        )

    if overture:
        overture_source = Source(
            provider="Overture Maps Foundation",
            dataset="buildings",
            reference=overture.get("gers_id"),
        )

        for label, key, unit in [
            ("building subtype", "subtype", None),
            ("building class", "class", None),
            ("height", "height", "m"),
            ("above-ground floors", "num_floors", None),
            ("roof material", "roof_material", None),
            ("roof shape", "roof_shape", None),
            ("roof ridge direction", "roof_direction", "degrees"),
        ]:
            value = overture.get(key)

            if present(value):
                facts.append(
                    Fact(
                        attribute=label,
                        value=value,
                        unit=unit,
                        status=EvidenceStatus.recorded,
                        source=overture_source,
                    )
                )

    constraint_facts = []

    constraint_entities = await get_constraints(
        lat,
        lon,
        uprn=uprn,
    )

    for entity in constraint_entities:
        dataset = entity.get("dataset", "planning-data")
        value = (
            entity.get("name")
            or entity.get("reference")
            or entity.get("entity")
        )

        constraint_facts.append(
            Fact(
                attribute=dataset,
                value=value,
                status=EvidenceStatus.recorded,
                confidence=1.0,
                source=Source(
                    provider="Planning Data",
                    dataset=dataset,
                    reference=str(entity.get("entity", "")),
                    licence_note=(
                        "Coverage varies. Absence of a returned record "
                        "is not proof that a constraint does not apply."
                    ),
                ),
            )
        )

    history = []

    planning_entities = await planning_history(
        lat,
        lon,
        uprn=uprn,
    )

    for index, entity in enumerate(planning_entities):
        reference = str(
            entity.get("reference")
            or entity.get("entity")
            or index
        )

        description = (
            entity.get("name")
            or entity.get("description")
            or f"Planning record {reference}"
        )

        event_date = (
            entity.get("entry-date")
            or entity.get("start-date")
        )

        history.append(
            Event(
                event_id=(
                    "planning_"
                    + hashlib.sha256(reference.encode()).hexdigest()[:10]
                ),
                event_type="planning_record",
                event_date=event_date,
                description=str(description),
                source=Source(
                    provider="Planning Data",
                    dataset="planning-application",
                    reference=reference,
                ),
                confidence=1.0,
            )
        )

    roof = build_roof(identity.record_id, facts)

    attributes = {fact.attribute for fact in facts}

    unknowns = [
        item
        for item in [
            "UPRN",
            "construction date",
            "original construction period",
            "building alteration chronology",
            "window installation date",
            "drainage condition",
        ]
        if item not in attributes
    ]

    return BuildingRecord(
        identity=identity,
        facts=facts,
        constraints=constraint_facts,
        components=[roof],
        history=history,
        unknowns=unknowns,
    )
