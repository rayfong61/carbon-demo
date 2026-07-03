import io

import main
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
    assert data["rag_kb_count"] == 5


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


def test_create_record_rejects_duplicate_sha(client):
    payload = {
        "file_name": "bill.png",
        "file_sha256": "same-sha-duplicate",
        "extraction_raw": DEMO_EXTRACTION,
        "confirmed": CONFIRMED,
    }
    r = client.post("/api/records", json=payload)
    assert r.status_code == 200

    r = client.post("/api/records", json=payload)
    assert r.status_code == 409
    assert "紀錄 #1" in r.json()["detail"]


def test_get_record_not_found(client):
    r = client.get("/api/records/9999")
    assert r.status_code == 404


def test_rag_demo_mode(client):
    r = client.post("/api/chat/rag", json={"query": "範疇二外購電力怎麼算"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"]
    assert data["source"]
    assert data["mode"] == "demo"
    assert isinstance(data["score"], float)


def test_rag_rejects_empty_query(client):
    r = client.post("/api/chat/rag", json={"query": ""})
    assert r.status_code == 422
    r = client.post("/api/chat/rag", json={"query": "   "})
    assert r.status_code == 422


def test_rag_app_usage_query(client):
    r = client.post("/api/chat/rag", json={"query": "這個系統怎麼用？"})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "demo"
    assert data["source"] == "碳盤查數據擷取 Demo 使用說明"
    assert "上傳" in data["answer"]


def test_rag_no_match(client):
    r = client.post("/api/chat/rag", json={"query": "今天天氣如何"})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "no_match"
    assert data["source"] is None


def test_rag_response_schema(client):
    r = client.post("/api/chat/rag", json={"query": "CBAM 是什麼"})
    assert r.status_code == 200
    data = r.json()
    for key in ("answer", "source", "source_url", "score", "low_confidence", "mode"):
        assert key in data


def test_rag_live_mode(client, monkeypatch):
    monkeypatch.setattr(main, "DEMO_MODE", False)
    monkeypatch.setattr(main, "call_claude_text", lambda prompt: "測試回答")
    r = client.post("/api/chat/rag", json={"query": "範疇二外購電力"})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "live"
    assert data["answer"] == "測試回答"


def test_rag_fallback_on_api_error(client, monkeypatch):
    monkeypatch.setattr(main, "DEMO_MODE", False)

    def boom(_):
        raise RuntimeError("api down")

    monkeypatch.setattr(main, "call_claude_text", boom)
    r = client.post("/api/chat/rag", json={"query": "範疇二外購電力"})
    assert r.status_code == 200
    assert r.json()["mode"] == "fallback"


def test_rag_stream_demo_mode(client):
    r = client.post("/api/chat/rag/stream", json={"query": "範疇二外購電力怎麼算"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    body = r.text
    assert '"type": "meta"' in body
    assert '"type": "chunk"' in body
    assert '"type": "done"' in body
