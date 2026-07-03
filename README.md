# 碳盤查數據擷取 Demo — 電費單 → 碳排數字

企業永續管理平台「碳盤查模組」的垂直切片示範：**上傳電費單 → AI 抽取 → 人工覆核 → 係數計算 → 可追溯紀錄**。

本專案聚焦 **GHG Protocol 範疇二（外購電力）** 這條最窄但完整的路徑，展示從原始憑證到可查證碳排數字的端到端流程。

**技術棧：** React (Vite) · FastAPI · SQLite · Claude Vision (Anthropic API)

---

## 目錄

- [系統架構](#系統架構)
- [專案結構](#專案結構)
- [資料流與 API](#資料流與-api)
- [資料庫設計](#資料庫設計)
- [核心設計決策](#核心設計決策)
- [環境需求與啟動](#環境需求與啟動)
- [操作說明（Demo 動線）](#操作說明demo-動線)
- [DEMO_MODE 備援機制](#demo_mode-備援機制)
- [本 Demo 範圍外](#本-demo-範圍外)

---

## 系統架構

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend  React + Vite  (localhost:5173)                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ 1.上傳   │ → │ 2.覆核   │ → │ 3.結果   │ → │ 追溯鏈 Modal │  │
│  │ 拖曳/選檔│   │ 低信心高亮│   │ 碳排計算 │   │ 完整證據鏈   │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ /api/* (Vite dev proxy)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend  FastAPI  (localhost:8000)                             │
│                                                                 │
│  POST /api/extract      影像 → SHA-256 → Claude Vision → 結構化欄位 + 信心分數
│  POST /api/records      覆核值入庫 → 係數快照 → 碳排計算
│  GET  /api/records      盤查紀錄列表
│  GET  /api/records/{id} 單筆完整追溯鏈
│  GET  /api/factors      版本化排放係數庫
│  GET  /api/health       健康檢查（含 demo_mode 狀態）
│                                                                 │
│  SQLite (carbon.db)  +  uploads/ (原始憑證,以 hash 命名去重)
└─────────────────────────────────────────────────────────────────┘
```

**三階段使用者流程：**

| 步驟 | 畫面 | 後端動作 |
|------|------|----------|
| 1. 上傳單據 | 拖曳或選擇電費單影像 | 計算 SHA-256、儲存憑證、呼叫 Vision API 抽取欄位 |
| 2. AI 抽取覆核 | 預填欄位，低信心（< 0.8）琥珀色高亮 | 回傳抽取結果與合理性警告，等待人工確認 |
| 3. 計算與追溯 | 顯示 tCO₂e、係數版本、稽核軌跡 | 入庫、快照係數、計算碳排，可展開完整追溯鏈 |

---

## 專案結構

```
carbon-demo/
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # 三步驟 UI、覆核表單、紀錄列表、追溯鏈 Modal
│   │   └── main.jsx
│   └── vite.config.js       # dev server 將 /api 代理至 :8000
├── backend/
│   ├── main.py              # FastAPI 主程式（抽取、入庫、追溯、係數庫）
│   ├── make_sample_bill.py  # 產生合成測試電費單（虛構資料）
│   ├── sample_bill.png      # 執行上述腳本後產生，供 Demo 使用
│   ├── requirements.txt
│   ├── .env.example         # ANTHROPIC_API_KEY 範本
│   ├── carbon.db            # SQLite（執行後自動建立，已 gitignore）
│   └── uploads/             # 上傳憑證儲存（已 gitignore）
└── README.md
```

---

## 資料流與 API

### `POST /api/extract`

上傳電費單影像，回傳 AI 抽取結果。

**輸入：** `multipart/form-data`，欄位 `file`（PNG / JPG / WebP，上限 10 MB）

**輸出重點：**

```json
{
  "file_name": "sample_bill.png",
  "file_sha256": "abc123...",
  "extraction": {
    "meter_number": "07-51-2088-13-6",
    "billing_start": "2026-04-01",
    "billing_end": "2026-05-31",
    "kwh": 42580,
    "amount_ntd": 128460,
    "confidence": { "kwh": 0.97, "amount_ntd": 0.64, "...": "..." }
  },
  "warnings": [],
  "mode": "demo"
}
```

- `mode`：`live`（真實 API）/ `demo`（無 API Key）/ `fallback`（API 失敗備援）
- 抽取欄位：電號、計費期間起迄、用電度數、應繳金額，各附 0–1 信心分數

### `POST /api/records`

人工覆核確認後入庫並計算碳排。

**輸入：**

```json
{
  "file_name": "...",
  "file_sha256": "...",
  "extraction_raw": { "...AI 原始抽取..." },
  "confirmed": { "meter_number": "...", "billing_start": "...", "billing_end": "...", "kwh": 42580, "amount_ntd": 128460 }
}
```

**輸出重點：** 紀錄 ID、碳排量（kgCO₂e / tCO₂e）、使用的係數快照、被人工修改的欄位列表。

**計算公式：** `emission_kgco2e = kWh × 排放係數 (kgCO2e/kWh)`

係數依帳單 `billing_end` 的年份自動選用（例如 2024 年帳單 → `2024.v1`）。

### `GET /api/records/{id}`

回傳單筆紀錄的完整追溯鏈：

1. 原始憑證（檔名 + SHA-256）
2. AI 抽取原始結果（不可變）
3. 人工覆核（哪些欄位被修改）
4. 係數快照（版本、數值、來源）
5. 最終計算結果

### `GET /api/factors`

回傳版本化排放係數庫（目前內建 2024.v1、2025.v1 台灣電力排碳係數）。

---

## 資料庫設計

SQLite 單表 `records`，每筆盤查紀錄包含：

| 欄位 | 說明 |
|------|------|
| `file_sha256` | 原始憑證雜湊，確保檔案完整性可追溯 |
| `extraction_raw` | AI 原始抽取 JSON（入庫後不可變） |
| `confirmed_fields` | 人工覆核後的最終值 |
| `edited_fields` | 被修改的欄位名稱陣列（稽核軌跡） |
| `factor_snapshot` | 計算當下係數的完整快照（版本、數值、來源） |
| `kwh` / `emission_kgco2e` | 活動數據與計算結果 |

---

## 核心設計決策

### 1. 人工覆核是需求，不是妥協

盤查數據須經第三方查證，每個數字都需要可歸責的確認節點。AI 的價值在於**把覆核成本降到趨近於零**（預填 + 低信心欄位高亮），而非取消覆核。信心 < 0.8 的欄位以琥珀色標示。

### 2. 係數版本化 Snapshot

電力排碳係數每年由能源署公告。紀錄入庫時將當年度係數**完整快照**存入該筆紀錄；未來係數更新**不回溯**改動歷史數據，否則已查證的報告會對不上。

### 3. 稽核軌跡

AI 原始抽取結果不可變地保存；人工修改過哪些欄位、原始檔 SHA-256、係數版本、計算時間全部可追溯，一鍵展開完整證據鏈。

### 4. 入庫前防呆

抽取後、入庫前執行合理性檢查：用電度數範圍（0–10,000,000 kWh）、計費期間起迄邏輯。起日晚於迄日時拒絕入庫。

---

## 環境需求與啟動

### 環境需求

- Python 3.10+
- Node.js 18+
- （選用）Anthropic API Key — 用於真實 Claude Vision 抽取

### 後端

```bash
cd backend
pip install -r requirements.txt
python make_sample_bill.py            # 產生合成測試電費單 sample_bill.png

# 選用：設定 API Key 以啟用真實抽取
cp .env.example .env
# 編輯 .env，填入 ANTHROPIC_API_KEY=sk-ant-...

uvicorn main:app --port 8000
```

後端啟動後可訪問 `http://localhost:8000/docs` 查看 Swagger API 文件。

### 前端

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

前端透過 Vite proxy 將 `/api` 請求轉發至 `http://localhost:8000`，**兩個服務需同時運行**。

### 健康檢查

```bash
curl http://localhost:8000/api/health
# {"status":"ok","demo_mode":true}
```

`demo_mode: true` 表示未設定 API Key，抽取端點使用預錄結果。

---

## 操作說明（Demo 動線）

建議使用 `backend/sample_bill.png` 進行現場展示（合成虛構資料，不含真實帳單或個資）。

### 約 2 分鐘展示腳本

1. **上傳** — 拖入 `sample_bill.png`，畫面顯示「AI 正在解析單據欄位…」
2. **覆核** — 指出「應繳金額信心 64%，系統自動高亮」→ 現場修改金額 → 說明「人工覆核是刻意設計，盤查數據要過第三方查證」
3. **入庫** — 點「確認入庫並計算碳排」→ 結果卡顯示 tCO₂e、係數版本與來源
4. **追溯** — 點「檢視追溯鏈」→ 展示：憑證 hash → AI 抽取 → 人工修改紀錄 → 係數快照 → 計算結果
5. **收尾** — 「這條路徑擴展到油單、冷媒紀錄就是範疇一；供應商填報入口就是範疇三。」

### UI 操作要點

| 操作 | 位置 |
|------|------|
| 上傳單據 | 首頁拖曳區或「選擇檔案」按鈕 |
| 覆核修改 | Step 2 表單，低信心欄位有琥珀色提示 |
| 確認入庫 | Step 2 底部「確認入庫並計算碳排」 |
| 查看追溯鏈 | Step 3「檢視追溯鏈」，或下方盤查紀錄表格的「追溯」連結 |
| 處理下一張 | Step 3「處理下一張單據」重置流程 |

---

## DEMO_MODE 備援機制

未設定 `ANTHROPIC_API_KEY`，或 API 呼叫失敗時，`/api/extract` 回傳與 `sample_bill.png` 內容一致的預錄結果，確保線上 Demo 穩定運行。

| `mode` 值 | 觸發條件 |
|-----------|----------|
| `live` | 成功呼叫 Claude Vision API |
| `demo` | 未設定 `ANTHROPIC_API_KEY` |
| `fallback` | 有 API Key 但呼叫失敗 |

前端覆核畫面在 non-live 模式下會顯示「預錄模式」標籤。

---

## 本 Demo 範圍外

以下功能在完整產品架構中規劃，但本垂直切片刻意不包含，以聚焦核心路徑：

- 登入與權限管理
- 範疇一（直接排放）/ 範疇三（價值鏈排放）
- 供應商填報入口
- 查證證據包匯出
- 報表輸出與儀表板

---

> 所有測試資料皆為合成虛構，不含任何真實帳單或個資。
