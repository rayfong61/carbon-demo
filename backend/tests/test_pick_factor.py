from main import pick_factor


def test_pick_factor_2024():
    factor = pick_factor("2024-06-30")
    assert factor["version"] == "2024.v1"
    assert factor["value"] == 0.494


def test_pick_factor_2025():
    factor = pick_factor("2025-01-15")
    assert factor["version"] == "2025.v1"
    assert factor["value"] == 0.474


def test_pick_factor_invalid_date_defaults_to_latest():
    factor = pick_factor("invalid")
    assert factor["version"] == "2025.v1"
