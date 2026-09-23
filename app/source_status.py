from enum import Enum
from pydantic import BaseModel, Field


class SourceState(str, Enum):
    success = "success"
    no_match = "no_match"
    unavailable = "unavailable"
    incomplete = "incomplete"


class SourceResult(BaseModel):
    state: SourceState
    records: list[dict] = Field(default_factory=list)
    note: str | None = None
