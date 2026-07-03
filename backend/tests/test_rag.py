from knowledge_base import KNOWLEDGE_BASE

from main import RAG_SCORE_THRESHOLD, retrieve_context


def test_knowledge_base_schema():
    assert len(KNOWLEDGE_BASE) >= 4
    for doc in KNOWLEDGE_BASE:
        assert doc["source"] and doc["content"] and doc["source_url"]
        assert doc["source_url"].startswith("https://")
        assert len(doc["content"]) >= 100


def test_retrieve_scope2_query():
    ctx = retrieve_context("範疇二外購電力怎麼算")
    assert "Scope 2" in ctx["source"] or "範疇" in ctx["source"]
    assert ctx["score"] > 0
    assert ctx["source_url"].startswith("https://")


def test_retrieve_cbam_query():
    ctx = retrieve_context("CBAM 進口商申報")
    assert "CBAM" in ctx["source"]
    assert ctx["score"] > RAG_SCORE_THRESHOLD


def test_retrieve_factor_query():
    ctx = retrieve_context("台灣電力排碳係數")
    assert "能源署" in ctx["source"] or "排碳係數" in ctx["source"]
    assert ctx["score"] > 0


def test_retrieve_no_match():
    ctx = retrieve_context("棒球賽幾點開始")
    assert ctx["score"] < RAG_SCORE_THRESHOLD
    assert ctx["matched"] is False


def test_retrieve_app_usage_query():
    for q in ("這個系統怎麼用？", "這個app用法", "系統怎麼用"):
        ctx = retrieve_context(q)
        assert ctx["source"] == "碳盤查數據擷取 Demo 使用說明"
        assert ctx["matched"] is True


def test_retrieve_app_usage_not_regulation_query():
    ctx = retrieve_context("範疇二外購電力怎麼算")
    assert "Scope 2" in ctx["source"] or "範疇" in ctx["source"]


def test_retrieve_context_structure():
    ctx = retrieve_context("範疇二")
    for key in ("source", "source_url", "content", "score", "matched"):
        assert key in ctx
