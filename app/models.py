from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    recorded = "recorded"
    estimated = "estimated"
    verified = "verified"
    unknown = "unknown"
    conflicting = "conflicting"


class Source(BaseModel):
    provider: str
    dataset: str
    reference: str | None = None
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    licence_note: str | None = None


class Fact(BaseModel):
    attribute: str
    value: Any = None
    unit: str | None = None
    status: EvidenceStatus = EvidenceStatus.unknown
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_date: str | None = None
    source: Source | None = None
    note: str | None = None


class BuildingIdentity(BaseModel):
    record_id: str
    address: str
    latitude: float
    longitude: float

    # Persistent external identifiers
    uprn: str | None = None
    gers_id: str | None = None

    # Identity evidence
    uprn_status: EvidenceStatus = EvidenceStatus.unknown
    uprn_confidence: float | None = Field(default=None, ge=0, le=1)
    uprn_source: Source | None = None


class Component(BaseModel):
    component_id: str
    component_type: str
    facts: list[Fact] = []


class Event(BaseModel):
    event_id: str
    event_type: str
    event_date: str | None = None
    description: str
    component_id: str | None = None
    source: Source | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class BuildingRecord(BaseModel):
    identity: BuildingIdentity
    facts: list[Fact] = []
    constraints: list[Fact] = []
    components: list[Component] = []
    history: list[Event] = []
    unknowns: list[str] = []
