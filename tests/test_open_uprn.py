from app.connectors.open_uprn import _distance_m, MAX_VERIFY_DISTANCE_M, AMBIGUITY_MARGIN_M


def test_distance_same_point_is_zero():
    assert _distance_m(53.212018, -0.817870, 53.212018, -0.817870) == 0


def test_uprn_verification_radius_is_conservative():
    assert MAX_VERIFY_DISTANCE_M <= 12.0


def test_ambiguity_margin_is_required():
    assert AMBIGUITY_MARGIN_M >= 4.0
