import { useEffect, useRef, useState } from 'react'
import AssistantMarkdown from './AssistantMarkdown'

const SUGGESTED_PROMPTS = [
  '這個系統怎麼用？',
  '範疇二外購電力怎麼算？',
  'CBAM 是什麼？',
  '台灣電力排碳係數從哪來？',
]

function parseSseBlock(block) {
  const line = block.split('\n').find(l => l.startsWith('data: '))
  if (!line) return null
  try {
    return JSON.parse(line.slice(6))
  } catch {
    return null
  }
}

export default function RegulationAssistant({ onClose }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)
  const msgIdRef = useRef(0)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  function nextMsgId() {
    msgIdRef.current += 1
    return msgIdRef.current
  }

  function patchMessage(id, patch) {
    setMessages(m => m.map(msg => (msg.id === id ? { ...msg, ...patch } : msg)))
  }

  async function send(query) {
    const text = query.trim()
    if (!text || busy) return
    setMessages(m => [...m, { id: nextMsgId(), role: 'user', text }])
    setInput('')
    setBusy(true)

    const assistantId = nextMsgId()
    setMessages(m => [
      ...m,
      { id: assistantId, role: 'assistant', text: '', streaming: true },
    ])

    try {
      const r = await fetch('/api/chat/rag/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text }),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || '問答失敗')
      }

      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const block of parts) {
          const ev = parseSseBlock(block)
          if (!ev) continue

          if (ev.type === 'meta') {
            patchMessage(assistantId, {
              source: ev.source,
              source_url: ev.source_url,
              low_confidence: ev.low_confidence,
              mode: ev.mode,
            })
          } else if (ev.type === 'chunk' && ev.text) {
            setMessages(m =>
              m.map(msg =>
                msg.id === assistantId
                  ? { ...msg, text: msg.text + ev.text }
                  : msg,
              ),
            )
          } else if (ev.type === 'done') {
            patchMessage(assistantId, {
              streaming: false,
              ...(ev.mode ? { mode: ev.mode } : {}),
            })
          }
        }
      }

      patchMessage(assistantId, { streaming: false })
    } catch (e) {
      patchMessage(assistantId, {
        text: e.message,
        streaming: false,
        source: null,
      })
    } finally {
      setBusy(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  return (
    <div className="assistant">
      <div className="assistant-header">
        <div>
          <h2>AI 永續法規小助手</h2>
          <p className="assistant-disclaimer">僅供學習展示，非法律意見</p>
        </div>
        {onClose && (
          <button type="button" className="assistant-close ghost" onClick={onClose} aria-label="關閉">
            關閉
          </button>
        )}
      </div>

      <div className="assistant-messages">
        {messages.length === 0 && (
          <p className="assistant-empty">詢問範疇二、CBAM 或台灣盤查相關問題</p>
        )}
        {messages.map(msg => (
          <div
            key={msg.id}
            className={`assistant-msg assistant-msg--${msg.role}${msg.streaming ? ' assistant-msg--streaming' : ''}`}
          >
            {msg.role === 'assistant' ? (
              <div
                className={`assistant-md${msg.streaming ? ' assistant-md--streaming' : ''}${msg.text ? ' assistant-md--has-text' : ''}`}
              >
                {msg.text ? (
                  <AssistantMarkdown>{msg.text}</AssistantMarkdown>
                ) : (
                  msg.streaming && (
                    <span className="assistant-typing">正在檢索與生成…</span>
                  )
                )}
              </div>
            ) : (
              <p>{msg.text}</p>
            )}
            {msg.role === 'assistant' && msg.source && !msg.streaming && (
              <span className={`source-badge${msg.low_confidence ? ' source-badge--low' : ''}`}>
                📄 來源：
                {msg.source_url ? (
                  <a href={msg.source_url} target="_blank" rel="noopener noreferrer">
                    {msg.source}
                  </a>
                ) : (
                  msg.source
                )}
              </span>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="assistant-prompts">
        {SUGGESTED_PROMPTS.map(p => (
          <button
            key={p}
            type="button"
            className="assistant-prompt-chip"
            disabled={busy}
            onClick={() => send(p)}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="assistant-input-row">
        <input
          type="text"
          placeholder="輸入法規問題…"
          value={input}
          disabled={busy}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button type="button" disabled={busy || !input.trim()} onClick={() => send(input)}>
          送出
        </button>
      </div>
    </div>
  )
}
