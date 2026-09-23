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


def test_different_validity_periods_are_not_conflicts():
    facts=[
        Fact(attribute="roof form",value="pitched",status=EvidenceStatus.recorded,valid_until="2019-12-31"),
        Fact(attribute="roof form",value="flat",status=EvidenceStatus.recorded,valid_from="2020-01-01"),
    ]
    assert not any(f.status == EvidenceStatus.conflicting for f in reconcile_facts(facts))


def test_reconciliation_is_idempotent():
    facts=[
        Fact(attribute="storeys",value=2,status=EvidenceStatus.recorded),
        Fact(attribute="storeys",value=3,status=EvidenceStatus.recorded),
    ]
    once=reconcile_facts(facts)
    twice=reconcile_facts(once)
    assert sum(f.status == EvidenceStatus.conflicting for f in once) == 1
    assert sum(f.status == EvidenceStatus.conflicting for f in twice) == 1


def test_equivalent_metric_units_do_not_conflict():
    facts=[
        Fact(attribute="height",value=10,status=EvidenceStatus.recorded,unit="m"),
        Fact(attribute="height",value=1000,status=EvidenceStatus.recorded,unit="cm"),
    ]
    assert not any(f.status == EvidenceStatus.conflicting for f in reconcile_facts(facts))
