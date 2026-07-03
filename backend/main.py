"""
碳盤查 Demo — 電費單 → 碳排數字 垂直切片
FastAPI backend: 文件抽取 (Claude Vision) → 人工覆核 → 係數計算 → 可追溯紀錄

環境變數:
  ANTHROPIC_API_KEY  未設定時自動進入 DEMO_MODE(回傳預錄抽取結果,面試備援用)
"""
import base64
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------- 基礎設定
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "carbon.db"

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEMO_MODE = not API_KEY  # 沒有金鑰就用預錄結果,live demo 永不翻車

app = FastAPI(title="Carbon Intake Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------- 排放係數庫(版本化)
# 重點設計:係數有 version 與 effective_year,盤查紀錄永遠 snapshot 當下係數,
# 未來係數更新不回溯改動歷史數據 —— 這是第三方查證的基本要求。
EMISSION_FACTORS = [
    {
        "factor_id": "TW-GRID-ELEC",
        "version": "2025.v1",
        "effective_year": 2025,
        "name": "台灣電力排碳係數",
        "value": 0.474,
        "unit": "kgCO2e/kWh",
        "source": "經濟部能源署 2025 年公告(demo 示意值,正式版以官方公告為準)",
    },
    {
        "factor_id": "TW-GRID-ELEC",
        "version": "2024.v1",
        "effective_year": 2024,
        "name": "台灣電力排碳係數",
        "value": 0.494,
        "unit": "kgCO2e/kWh",
        "source": "經濟部能源署 2024 年公告(demo 示意值)",
    },
]


def pick_factor(billing_end: str) -> dict:
    """依帳單期間結束日的年份選用當年度係數版本。"""
    try:
        year = int(str(billing_end)[:4])
    except (ValueError, TypeError):
        year = 2025
    candidates = [f for f in EMISSION_FACTORS if f["effective_year"] <= year]
    return max(candidates, key=lambda f: f["effective_year"]) if candidates else EMISSION_FACTORS[0]


# ---------------------------------------------------------------- SQLite
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


with db() as conn:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            file_name TEXT,
            file_sha256 TEXT,
            extraction_raw TEXT,      -- AI 原始抽取結果(不可變)
            confirmed_fields TEXT,    -- 人工覆核後的最終值
            edited_fields TEXT,       -- 哪些欄位被人工修改過(稽核軌跡)
            factor_snapshot TEXT,     -- 計算當下的係數完整快照
            kwh REAL,
            emission_kgco2e REAL,
            status TEXT DEFAULT 'confirmed'
        )"""
    )

# ---------------------------------------------------------------- 抽取
EXTRACTION_PROMPT = """你是碳盤查系統的單據抽取引擎。請從這張台灣電力公司電費單影像中抽取以下欄位,
只回傳 JSON,不要任何其他文字或 markdown 標記:

{
  "meter_number": "電號(11碼,格式如 XX-XX-XXXX-XX-X,找不到填 null)",
  "billing_start": "計費期間起日 YYYY-MM-DD(民國年請轉西元)",
  "billing_end": "計費期間迄日 YYYY-MM-DD",
  "kwh": 用電度數(數字),
  "amount_ntd": 應繳金額新台幣(數字),
  "confidence": {
    "meter_number": 0.0~1.0,
    "billing_start": 0.0~1.0,
    "billing_end": 0.0~1.0,
    "kwh": 0.0~1.0,
    "amount_ntd": 0.0~1.0
  }
}

信心分數原則:欄位清晰可讀給 0.9 以上;模糊、被遮蔽或需要推測給 0.7 以下;完全找不到給 0 並將值設為 null。"""

DEMO_EXTRACTION = {
    "meter_number": "07-51-2088-13-6",
    "billing_start": "2026-04-01",
    "billing_end": "2026-05-31",
    "kwh": 42580,
    "amount_ntd": 128460,
    "confidence": {
        "meter_number": 0.95,
        "billing_start": 0.92,
        "billing_end": 0.92,
        "kwh": 0.97,
        "amount_ntd": 0.64,
    },
}


def call_claude_vision(image_bytes: bytes, media_type: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }
        ],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def validate(fields: dict) -> list[str]:
    """基本合理性檢查 —— 抽取後、入庫前的防呆。"""
    warnings = []
    kwh = fields.get("kwh")
    if kwh is not None and (kwh <= 0 or kwh > 10_000_000):
        warnings.append("用電度數超出合理範圍,請確認")
    start, end = fields.get("billing_start"), fields.get("billing_end")
    if start and end and str(start) >= str(end):
        warnings.append("計費期間起日晚於迄日")
    return warnings


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "檔案超過 10MB")
    sha = hashlib.sha256(data).hexdigest()
    ext = Path(file.filename or "bill.png").suffix or ".png"
    saved = UPLOAD_DIR / f"{sha}{ext}"
    saved.write_bytes(data)

    if DEMO_MODE:
        time.sleep(1.2)  # 模擬呼叫延遲,demo 動線更真實
        extraction = dict(DEMO_EXTRACTION)
        mode = "demo"
    else:
        media_type = file.content_type or "image/png"
        if media_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            media_type = "image/png"
        try:
            extraction = call_claude_vision(data, media_type)
            mode = "live"
        except Exception:
            extraction = dict(DEMO_EXTRACTION)  # API 失敗時的備援
            mode = "fallback"

    return {
        "file_name": file.filename,
        "file_sha256": sha,
        "extraction": extraction,
        "warnings": validate(extraction),
        "mode": mode,
    }


# ---------------------------------------------------------------- 確認入庫 + 計算
class ConfirmPayload(BaseModel):
    file_name: str
    file_sha256: str
    extraction_raw: dict
    confirmed: dict  # 覆核後最終值: meter_number / billing_start / billing_end / kwh / amount_ntd


@app.post("/api/records")
def create_record(p: ConfirmPayload):
    warnings = validate(p.confirmed)
    if any("起日晚於迄日" in w for w in warnings):
        raise HTTPException(422, warnings[0])

    kwh = float(p.confirmed.get("kwh") or 0)
    if kwh <= 0:
        raise HTTPException(422, "用電度數必須大於 0")

    factor = pick_factor(p.confirmed.get("billing_end", ""))
    emission = round(kwh * factor["value"], 2)

    # 稽核軌跡:比對 AI 原始值與人工確認值,記下被修改的欄位
    edited = [
        k for k in ("meter_number", "billing_start", "billing_end", "kwh", "amount_ntd")
        if str(p.extraction_raw.get(k)) != str(p.confirmed.get(k))
    ]

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO records
               (created_at, file_name, file_sha256, extraction_raw,
                confirmed_fields, edited_fields, factor_snapshot, kwh, emission_kgco2e)
               VALUES (datetime('now','localtime'),?,?,?,?,?,?,?,?)""",
            (
                p.file_name,
                p.file_sha256,
                json.dumps(p.extraction_raw, ensure_ascii=False),
                json.dumps(p.confirmed, ensure_ascii=False),
                json.dumps(edited, ensure_ascii=False),
                json.dumps(factor, ensure_ascii=False),
                kwh,
                emission,
            ),
        )
        record_id = cur.lastrowid

    return {
        "id": record_id,
        "kwh": kwh,
        "factor": factor,
        "emission_kgco2e": emission,
        "emission_tco2e": round(emission / 1000, 4),
        "edited_fields": edited,
        "warnings": warnings,
    }


@app.get("/api/records")
def list_records():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, created_at, file_name, kwh, emission_kgco2e FROM records ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/records/{record_id}")
def get_record(record_id: int):
    """完整追溯鏈:原始檔 hash → AI 抽取 → 人工修改 → 係數快照 → 結果。"""
    with db() as conn:
        row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "紀錄不存在")
    d = dict(row)
    for k in ("extraction_raw", "confirmed_fields", "edited_fields", "factor_snapshot"):
        d[k] = json.loads(d[k])
    return d


@app.get("/api/factors")
def factors():
    return EMISSION_FACTORS


@app.get("/api/health")
def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}
