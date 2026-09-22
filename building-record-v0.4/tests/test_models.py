from app.models import Fact, EvidenceStatus

def test_unknown_is_explicit():
    f = Fact(attribute="roof replacement date")
    assert f.status == EvidenceStatus.unknown
    assert f.value is None
