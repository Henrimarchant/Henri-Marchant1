import pytest

from app.connectors.geocoder import _score, _normalise_postcode
from app.models import EvidenceStatus
from app.services import stable_record_id


def candidate(name, postcode):
    return {
        "display_name": name,
        "address": {"postcode": postcode},
        "type": "house",
        "importance": 0.2,
    }


def test_postcode_normalisation():
    assert _normalise_postcode("ng25 0ps") == "NG250PS"


def test_wrong_postcode_is_rejected():
    item = candidate("Normanton Hall, Derby", "DE23 6XX")
    assert _score("Normanton Hall, NG25 0PS", item, "NG250PS") < 0


def test_matching_postcode_can_score():
    item = candidate("Normanton Hall, Southwell", "NG25 0PS")
    assert _score("Normanton Hall, NG25 0PS", item, "NG250PS") > 0


def test_unverified_uprn_must_not_drive_record_id():
    coordinates_id = stable_record_id(53.212018, -0.817870, None)
    arbitrary_uprn_id = stable_record_id(53.212018, -0.817870, "123")
    assert coordinates_id != arbitrary_uprn_id


def test_evidence_status_has_unknown_and_conflicting():
    assert EvidenceStatus.unknown.value == "unknown"
    assert EvidenceStatus.conflicting.value == "conflicting"


def test_postcode_only_has_no_unique_property_tokens():
    import re
    from app.connectors.geocoder import POSTCODE_RE
    query = "NG25 0PS"
    assert not POSTCODE_RE.sub("", query).strip(" ,")


def test_same_postcode_wrong_name_scores_lower():
    right = candidate("Normanton Hall, Southwell", "NG25 0PS")
    wrong = candidate("Another House, Southwell", "NG25 0PS")
    assert _score("Normanton Hall, NG25 0PS", right, "NG250PS") > _score(
        "Normanton Hall, NG25 0PS", wrong, "NG250PS"
    )


def test_address_without_postcode_is_rejected():
    import asyncio
    import pytest
    from app.connectors.geocoder import geocode_address
    with pytest.raises(ValueError, match="full property address including postcode"):
        asyncio.run(geocode_address("Normanton Hall, Normanton Road"))
