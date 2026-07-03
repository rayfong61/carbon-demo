# 碳盤查數據擷取 Demo — 電費單 → 碳排數字

企業永續管理平台「碳盤查模組」的垂直切片:
**上傳電費單 → AI 抽取 → 人工覆核 → 係數計算 → 可追溯紀錄**

React + FastAPI + SQLite + Claude Vision(Anthropic API)

```
frontend (React/Vite) ──/api proxy──> backend (FastAPI)
                                        ├─ /api/extract   影像 → LLM Vision → 結構化欄位 + 信心分數
                                        ├─ /api/records   覆核值入庫 → 活動數據 × 係數快照 → 碳排
                                        ├─ /api/records/N 追溯鏈(憑證 hash → 抽取 → 修改 → 係數 → 結果)
                                        └─ /api/factors   版本化排放係數庫
```

## 快速啟動

```bash
# 後端
cd backend
pip install -r requirements.txt
python make_sample_bill.py            # 產生合成測試電費單(虛構資料)
export ANTHROPIC_API_KEY=sk-ant-...   # 不設定則自動進入 DEMO_MODE(預錄結果)
uvicorn main:app --port 8000

# 前端(另開終端)
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

## DEMO_MODE(面試備援)

未設定 `ANTHROPIC_API_KEY`,或 API 呼叫失敗時,`/api/extract` 回傳與
`sample_bill.png` 內容一致的預錄結果 —— **線上面試 live demo 永不翻車**。
回應中的 `mode` 欄位標示 `live` / `demo` / `fallback`。

## 刻意的設計決策(面試講這些)

1. **人工覆核不是妥協,是需求。** 盤查數據須經第三方查證,每個數字要有可歸責
   的確認節點。AI 的工作是把覆核成本降到趨近於零(預填 + 低信心欄位高亮),
   不是取消覆核。信心 < 0.8 的欄位以琥珀色標示。
2. **係數版本化 snapshot。** 電力排碳係數每年由能源署公告。紀錄入庫時將當年度
   係數完整快照存入該筆紀錄,未來係數更新不回溯改動歷史數據 —— 否則已查證的
   報告會對不上。2024 年帳單自動選用 2024.v1 係數。
3. **稽核軌跡。** AI 原始抽取結果不可變地保存;人工修改過哪些欄位、原始檔
   SHA-256、係數版本、計算時間全部可追溯,一鍵展開完整證據鏈。
4. **入庫前防呆。** 度數合理範圍、計費期間起迄邏輯檢查,LLM 抽取結果永遠
   先驗證再落地。

## 範圍外(完整架構見提案文件)

登入權限、範疇一/三、供應商填報、查證證據包匯出、報表輸出 —— 本 demo 聚焦
範疇二外購電力這一條最窄但完整的路徑。

## 2 分鐘 Demo 動線

1. 拖入 `backend/sample_bill.png` → 「AI 正在解析單據欄位…」
2. 覆核畫面:指出「應繳金額信心 64%,系統自動高亮」→ 現場把金額改掉
   →「這裡刻意設計人工覆核,因為盤查數據要過第三方查證」
3. 確認入庫 → 結果卡:指「係數版本 2025.v1 與來源直接標在結果上」
4. 點「檢視追溯鏈」→ 展示 憑證 hash → AI 抽取 → 人工修改紀錄 → 係數快照 → 結果
5. 收尾:「這條路徑擴展到油單、冷媒紀錄就是範疇一;供應商填報入口就是範疇三。」

---
所有測試資料皆為合成虛構,不含任何真實帳單或個資。
