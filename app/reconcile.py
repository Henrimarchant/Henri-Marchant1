from .models import EvidenceStatus, Fact


def reconcile_facts(facts: list[Fact]) -> list[Fact]:
    """Preserve source facts and surface material contradictions explicitly."""
    grouped: dict[str, list[Fact]] = {}
    for fact in facts:
        grouped.setdefault(fact.attribute.strip().lower(), []).append(fact)

    output=list(facts)
    for _, group in grouped.items():
        known=[f for f in group if f.status != EvidenceStatus.unknown and f.value is not None]
        values={str(f.value).strip().lower() for f in known}
        if len(values) <= 1:
            continue
        best=max((f.confidence or 0 for f in known), default=0)
        output.append(Fact(
            attribute=known[0].attribute,
            value="Conflicting evidence",
            status=EvidenceStatus.conflicting,
            confidence=best,
            note="Sources disagree. Original evidence has been preserved; no value was silently selected.",
        ))
    return output
