from app.models import EvidenceStatus, Fact
from app.reconcile import reconcile_facts


def test_conflicting_values_are_preserved_and_flagged():
    a=Fact(attribute="roof form",value="pitched",status=EvidenceStatus.recorded,confidence=.8)
    b=Fact(attribute="roof form",value="flat",status=EvidenceStatus.recorded,confidence=.9)
    result=reconcile_facts([a,b])
    assert a in result and b in result
    assert any(x.status == EvidenceStatus.conflicting for x in result)


def test_matching_values_do_not_create_conflict():
    a=Fact(attribute="storeys",value=3,status=EvidenceStatus.recorded)
    b=Fact(attribute="storeys",value=3,status=EvidenceStatus.verified)
    assert not any(x.status == EvidenceStatus.conflicting for x in reconcile_facts([a,b]))
