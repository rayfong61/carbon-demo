from main import validate


def test_validate_ok():
    fields = {
        "kwh": 160,
        "billing_start": "2024-01-01",
        "billing_end": "2024-02-01",
    }
    assert validate(fields) == []


def test_validate_kwh_out_of_range():
    assert "用電度數超出合理範圍" in validate({"kwh": 0})[0]
    assert "用電度數超出合理範圍" in validate({"kwh": -5})[0]
    assert "用電度數超出合理範圍" in validate({"kwh": 10_000_001})[0]


def test_validate_billing_period():
    fields = {"billing_start": "2024-06-01", "billing_end": "2024-01-01"}
    assert validate(fields) == ["計費期間起日晚於迄日"]
