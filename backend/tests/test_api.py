import io

from main import DEMO_EXTRACTION

CONFIRMED = {
    "meter_number": DEMO_EXTRACTION["meter_number"],
    "billing_start": "2024-04-01",
    "billing_end": "2024-05-31",
    "kwh": 1000,
    "amount_ntd": DEMO_EXTRACTION["amount_ntd"],
}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["demo_mode"] is True


def test_factors(client):
    r = client.get("/api/factors")
    assert r.status_code == 200
    factors = r.json()
    assert len(factors) >= 2
    assert factors[0]["factor_id"] == "TW-GRID-ELEC"


def test_extract_demo_mode(client):
    # 最小合法 PNG（1×1 透明像素）
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.post(
        "/api/extract",
        files={"file": ("bill.png", io.BytesIO(png), "image/png")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "demo"
    assert data["extraction"]["kwh"] == DEMO_EXTRACTION["kwh"]
    assert "file_sha256" in data
    assert data["warnings"] == []


def test_create_record_and_trace(client):
    payload = {
        "file_name": "bill.png",
        "file_sha256": "deadbeef",
        "extraction_raw": DEMO_EXTRACTION,
        "confirmed": CONFIRMED,
    }
    r = client.post("/api/records", json=payload)
    assert r.status_code == 200
    created = r.json()
    assert created["kwh"] == 1000
    assert created["factor"]["version"] == "2024.v1"
    assert created["emission_kgco2e"] == 494.0
    assert created["emission_tco2e"] == 0.494
    assert created["edited_fields"] == ["billing_start", "billing_end", "kwh"]

    r = client.get("/api/records")
    assert r.status_code == 200
    records = r.json()
    assert len(records) == 1
    assert records[0]["id"] == created["id"]

    r = client.get(f"/api/records/{created['id']}")
    assert r.status_code == 200
    trace = r.json()
    assert trace["extraction_raw"]["kwh"] == DEMO_EXTRACTION["kwh"]
    assert trace["factor_snapshot"]["version"] == "2024.v1"
    assert trace["emission_kgco2e"] == 494.0


def test_create_record_tracks_edited_fields(client):
    confirmed = {**CONFIRMED, "kwh": 999}
    payload = {
        "file_name": "bill.png",
        "file_sha256": "abc",
        "extraction_raw": DEMO_EXTRACTION,
        "confirmed": confirmed,
    }
    r = client.post("/api/records", json=payload)
    assert r.status_code == 200
    assert r.json()["edited_fields"] == ["billing_start", "billing_end", "kwh"]


def test_create_record_rejects_invalid_period(client):
    payload = {
        "file_name": "bill.png",
        "file_sha256": "abc",
        "extraction_raw": DEMO_EXTRACTION,
        "confirmed": {
            **CONFIRMED,
            "billing_start": "2024-06-01",
            "billing_end": "2024-01-01",
        },
    }
    r = client.post("/api/records", json=payload)
    assert r.status_code == 422


def test_create_record_rejects_zero_kwh(client):
    payload = {
        "file_name": "bill.png",
        "file_sha256": "abc",
        "extraction_raw": DEMO_EXTRACTION,
        "confirmed": {**CONFIRMED, "kwh": 0},
    }
    r = client.post("/api/records", json=payload)
    assert r.status_code == 422


def test_get_record_not_found(client):
    r = client.get("/api/records/9999")
    assert r.status_code == 404
