from datetime import date
from .models import EvidenceStatus, Fact


def _date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _overlap(a: Fact, b: Fact) -> bool:
    """Different historical periods are not contradictory evidence."""
    a_start, a_end = _date(a.valid_from), _date(a.valid_until)
    b_start, b_end = _date(b.valid_from), _date(b.valid_until)
    if a_end and b_start and a_end < b_start:
        return False
    if b_end and a_start and b_end < a_start:
        return False
    return True


def _normal_value(fact: Fact):
    value=fact.value
    if isinstance(value, (int,float)) and not isinstance(value,bool):
        unit=(fact.unit or "").strip().lower()
        conversions={"mm":0.001,"cm":0.01,"m":1.0}
        if unit in conversions:
            return ("length_m", round(float(value)*conversions[unit], 4))
        return ("number", round(float(value), 6), unit)
    return ("text", " ".join(str(value).strip().lower().split()), (fact.unit or "").lower())


def reconcile_facts(facts: list[Fact]) -> list[Fact]:
    """Preserve evidence and add one idempotent conflict marker per attribute."""
    originals=[f for f in facts if f.status != EvidenceStatus.conflicting]
    grouped: dict[str,list[Fact]]={}
    for fact in originals:
        grouped.setdefault(fact.attribute.strip().lower(),[]).append(fact)

    output=list(originals)
    for group in grouped.values():
        known=[f for f in group if f.status != EvidenceStatus.unknown and f.value is not None]
        conflict=False
        for i,a in enumerate(known):
            for b in known[i+1:]:
                if _overlap(a,b) and _normal_value(a) != _normal_value(b):
                    conflict=True
                    break
            if conflict:
                break
        if not conflict:
            continue
        output.append(Fact(
            attribute=known[0].attribute,
            value="Conflicting evidence",
            status=EvidenceStatus.conflicting,
            confidence=max((f.confidence or 0 for f in known),default=0),
            note="Sources disagree for overlapping validity periods. Original evidence is preserved; no value was silently selected.",
        ))
    return output
