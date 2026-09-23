from app.models import EvidenceStatus


def test_recorded_and_verified_are_distinct():
    assert EvidenceStatus.recorded != EvidenceStatus.verified


def test_coordinate_candidate_does_not_imply_verified():
    candidate={"uprn":"100000000001","status":EvidenceStatus.recorded,"confidence":0.85}
    assert candidate["status"] == EvidenceStatus.recorded
    assert candidate["status"] != EvidenceStatus.verified
