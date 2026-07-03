import { useEffect, useRef, useState } from 'react'

const FIELD_META = [
  { key: 'meter_number', label: '電號', type: 'text' },
  { key: 'billing_start', label: '計費期間(起)', type: 'date' },
  { key: 'billing_end', label: '計費期間(迄)', type: 'date' },
  { key: 'kwh', label: '用電度數 (kWh)', type: 'number' },
  { key: 'amount_ntd', label: '應繳金額 (NT$)', type: 'number' },
]

const CONF_THRESHOLD = 0.8

export default function App() {
  const [step, setStep] = useState(1)               // 1 上傳 → 2 覆核 → 3 結果
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [extractResp, setExtractResp] = useState(null)
  const [fields, setFields] = useState({})
  const [result, setResult] = useState(null)
  const [records, setRecords] = useState([])
  const [trace, setTrace] = useState(null)
  const [preview, setPreview] = useState(null)
  const fileRef = useRef(null)

  const loadRecords = () =>
    fetch('/api/records').then(r => r.json()).then(setRecords).catch(() => {})
  useEffect(() => { loadRecords() }, [])

  // ---- Step 1:上傳 + AI 抽取 ----
  async function handleFile(file) {
    if (!file) return
    setError(''); setBusy(true)
    setPreview(URL.createObjectURL(file))
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch('/api/extract', { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json()).detail || '抽取失敗')
      const data = await r.json()
      setExtractResp(data)
      setFields({ ...data.extraction })
      setStep(2)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  // ---- Step 2 → 3:確認入庫 + 計算 ----
  async function confirm() {
    setError(''); setBusy(true)
    try {
      const r = await fetch('/api/records', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_name: extractResp.file_name,
          file_sha256: extractResp.file_sha256,
          extraction_raw: extractResp.extraction,
          confirmed: {
            meter_number: fields.meter_number,
            billing_start: fields.billing_start,
            billing_end: fields.billing_end,
            kwh: Number(fields.kwh),
            amount_ntd: Number(fields.amount_ntd),
          },
        }),
      })
      if (!r.ok) throw new Error((await r.json()).detail || '入庫失敗')
      setResult(await r.json())
      setStep(3)
      loadRecords()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setStep(1); setExtractResp(null); setFields({}); setResult(null)
    setPreview(null); setError('')
    if (fileRef.current) fileRef.current.value = ''
  }

  async function openTrace(id) {
    const r = await fetch(`/api/records/${id}`)
    setTrace(await r.json())
  }

  const conf = extractResp?.extraction?.confidence || {}

  return (
    <div className="page">
      <header>
        <div className="brand">
          <span className="brand-mark">CO₂e</span>
          <div>
            <h1>碳盤查數據擷取</h1>
            <p>電費單 → 碳排數字 垂直切片 Demo|範疇二・外購電力</p>
          </div>
        </div>
        <ol className="steps">
          {['上傳單據', 'AI 抽取覆核', '計算與追溯'].map((s, i) => (
            <li key={s} className={step === i + 1 ? 'on' : step > i + 1 ? 'done' : ''}>
              <span>{i + 1}</span>{s}
            </li>
          ))}
        </ol>
      </header>

      {error && <div className="alert">{error}</div>}

      {/* ---------------- Step 1 ---------------- */}
      {step === 1 && (
        <section
          className="drop"
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); handleFile(e.dataTransfer.files[0]) }}
        >
          {busy ? (
            <p className="pulse">AI 正在解析單據欄位…</p>
          ) : (
            <>
              <p>拖曳電費單影像到此處,或</p>
              <button onClick={() => fileRef.current.click()}>選擇檔案</button>
              <input
                ref={fileRef} type="file" accept="image/*" hidden
                onChange={e => handleFile(e.target.files[0])}
              />
              <p className="hint">支援 PNG / JPG,單檔 10MB 內。測試可用 backend/sample_bill.png</p>
            </>
          )}
        </section>
      )}

      {/* ---------------- Step 2:覆核 ---------------- */}
      {step === 2 && extractResp && (
        <section className="review">
          <div className="review-doc">
            {preview && <img src={preview} alt="上傳的單據" />}
            <p className="doc-meta">
              SHA-256:<code>{extractResp.file_sha256.slice(0, 16)}…</code>
              {extractResp.mode !== 'live' && <span className="tag">預錄模式</span>}
            </p>
          </div>
          <div className="review-form">
            <h2>覆核 AI 抽取結果</h2>
            <p className="sub">
              低信心欄位已標示,請確認後入庫。人工覆核是刻意設計:盤查數據須經第三方查證,每個數字都要有可歸責的確認節點。
            </p>
            {FIELD_META.map(({ key, label, type }) => {
              const low = (conf[key] ?? 1) < CONF_THRESHOLD
              const edited = String(fields[key] ?? '') !== String(extractResp.extraction[key] ?? '')
              return (
                <label key={key} className={low ? 'low' : ''}>
                  <span>
                    {label}
                    {low && <em>信心 {Math.round((conf[key] ?? 0) * 100)}%,請確認</em>}
                    {edited && <em className="edited">已修改</em>}
                  </span>
                  <input
                    type={type}
                    value={fields[key] ?? ''}
                    onChange={e => setFields({ ...fields, [key]: e.target.value })}
                  />
                </label>
              )
            })}
            {extractResp.warnings?.length > 0 && (
              <div className="warn">{extractResp.warnings.join(';')}</div>
            )}
            <div className="actions">
              <button className="ghost" onClick={reset}>取消</button>
              <button onClick={confirm} disabled={busy}>
                {busy ? '計算中…' : '確認入庫並計算碳排'}
              </button>
            </div>
          </div>
        </section>
      )}

      {/* ---------------- Step 3:結果 ---------------- */}
      {step === 3 && result && (
        <section className="result">
          <div className="result-card">
            <p className="result-label">本期外購電力碳排(範疇二)</p>
            <p className="result-num">
              {result.emission_tco2e.toLocaleString()} <small>tCO₂e</small>
            </p>
            <p className="result-calc">
              {Number(result.kwh).toLocaleString()} kWh × {result.factor.value} {result.factor.unit}
            </p>
            <div className="factor-chip">
              係數版本 <b>{result.factor.version}</b>|{result.factor.source}
            </div>
            {result.edited_fields.length > 0 && (
              <p className="edited-note">
                稽核軌跡:人工修改了 {result.edited_fields.length} 個欄位({result.edited_fields.join(', ')})
              </p>
            )}
          </div>
          <div className="actions center">
            <button className="ghost" onClick={() => openTrace(result.id)}>檢視追溯鏈</button>
            <button onClick={reset}>處理下一張單據</button>
          </div>
        </section>
      )}

      {/* ---------------- 紀錄列表 ---------------- */}
      {records.length > 0 && (
        <section className="records">
          <h2>盤查紀錄</h2>
          <table>
            <thead>
              <tr><th>#</th><th>時間</th><th>檔案</th><th className="num">kWh</th><th className="num">kgCO₂e</th><th /></tr>
            </thead>
            <tbody>
              {records.map(r => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.created_at}</td>
                  <td>{r.file_name}</td>
                  <td className="num">{Number(r.kwh).toLocaleString()}</td>
                  <td className="num">{Number(r.emission_kgco2e).toLocaleString()}</td>
                  <td><button className="link" onClick={() => openTrace(r.id)}>追溯</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ---------------- 追溯鏈 Modal ---------------- */}
      {trace && (
        <div className="modal-bg" onClick={() => setTrace(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>紀錄 #{trace.id} 追溯鏈</h2>
            <ol className="chain">
              <li>
                <b>原始憑證</b>
                <span>{trace.file_name}|SHA-256 <code>{trace.file_sha256.slice(0, 24)}…</code></span>
              </li>
              <li>
                <b>AI 抽取(不可變原始結果)</b>
                <pre>{JSON.stringify(trace.extraction_raw, null, 2)}</pre>
              </li>
              <li>
                <b>人工覆核</b>
                <span>
                  {trace.edited_fields.length
                    ? `修改欄位:${trace.edited_fields.join(', ')}`
                    : '未修改,直接確認'}
                </span>
              </li>
              <li>
                <b>係數快照</b>
                <span>
                  {trace.factor_snapshot.name} {trace.factor_snapshot.version} ={' '}
                  {trace.factor_snapshot.value} {trace.factor_snapshot.unit}
                </span>
              </li>
              <li>
                <b>計算結果</b>
                <span>
                  {Number(trace.kwh).toLocaleString()} kWh → <b>{Number(trace.emission_kgco2e).toLocaleString()} kgCO₂e</b>
                  |{trace.created_at}
                </span>
              </li>
            </ol>
            <button className="ghost" onClick={() => setTrace(null)}>關閉</button>
          </div>
        </div>
      )}

      <footer>Demo by Ray Lu|架構完整版見 README 與提案文件</footer>
    </div>
  )
}
