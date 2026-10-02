import { useCallback, useEffect, useRef, useState } from 'react'
import delphiIcon from './icons/delphi.png'
import { api, type DelphiMessage } from './api'

/**
 * Delphi, the chat agent: a small floating orb that stands apart from every screen. A click opens her
 * chat; dragging the orb moves it out of the way of the documents. She answers only about the documents
 * of the active werkmap and about Apollo itself, and thinks along about conflicts between documents.
 */

const INTRO =
  'Hoi, ik ben Delphi. Vraag me alles over de documenten in deze werkmap of over Apollo zelf — daar denk ik graag met je mee.'

type DragState =
  | { kind: 'idle' }
  | { kind: 'press'; startX: number; startY: number; orbX: number; orbY: number; moved: boolean }
  | { kind: 'drag'; dx: number; dy: number }

const CLOSED_POS_KEY = 'apollo.delphiOrbPos'

function loadPos(): { x: number; y: number } {
  try {
    const raw = localStorage.getItem(CLOSED_POS_KEY)
    if (raw) {
      const p = JSON.parse(raw) as { x: number; y: number }
      if (Number.isFinite(p.x) && Number.isFinite(p.y)) return { x: p.x, y: p.y }
    }
  } catch {
    /* fall through to the default */
  }
  return { x: 0, y: 0 }
}

export default function DelphiChat({ workspaceId }: { workspaceId: number | null }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(loadPos)
  const [drag, setDrag] = useState<DragState>({ kind: 'idle' })
  const [messages, setMessages] = useState<DelphiMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const orbRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (workspaceId == null) return
    let cancelled = false
    api
      .delphiHistory(workspaceId)
      .then((h) => {
        if (!cancelled) setMessages(h)
      })
      .catch(() => {
        /* a new werkmap simply starts empty */
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages, busy, open])

  // Dragging the orb: keep the cursor offset constant and stay inside the window.
  useEffect(() => {
    if (drag.kind !== 'drag') return
    const onMove = (e: MouseEvent) => {
      const w = orbRef.current?.offsetWidth ?? 56
      const maxX = window.innerWidth - w - 8
      const maxY = window.innerHeight - w - 8
      setPos({
        x: Math.min(Math.max(e.clientX + drag.dx, 8), Math.max(8, maxX)),
        y: Math.min(Math.max(e.clientY + drag.dy, 8), Math.max(8, maxY)),
      })
    }
    const onUp = () => setDrag({ kind: 'idle' })
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [drag])

  useEffect(() => {
    localStorage.setItem(CLOSED_POS_KEY, JSON.stringify(pos))
  }, [pos])

  const onOrbMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return
    const rect = orbRef.current?.getBoundingClientRect()
    setDrag({
      kind: 'press',
      startX: e.clientX,
      startY: e.clientY,
      orbX: rect?.left ?? 0,
      orbY: rect?.top ?? 0,
      moved: false,
    })
  }

  useEffect(() => {
    if (drag.kind !== 'press') return
    const onMove = (e: MouseEvent) => {
      if (!drag.moved && Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 4) return
      setDrag({ kind: 'drag', dx: drag.orbX - drag.startX, dy: drag.orbY - drag.startY })
    }
    const onUp = () => {
      if (!drag.moved) setOpen((v) => !v) // a press that never moved is a click: it opens (or closes) Delphi
      setDrag({ kind: 'idle' })
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [drag])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || busy || workspaceId == null) return
    const followUpOf = messages.length > 0 ? messages[messages.length - 1].id : null
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const result = await api.delphiChat(text, workspaceId, followUpOf)
      setMessages((m) => [...m, result.user_message, result.reply])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }, [input, busy, workspaceId, messages])

  if (workspaceId == null) return null

  return (
    <div className="fixed inset-0 z-50 pointer-events-none" aria-hidden={!open}>
      <div
        ref={orbRef}
        onMouseDown={onOrbMouseDown}
        title="Delphi — klik om te openen, sleep om uit de weg te gaan"
        className={`pointer-events-auto absolute flex h-14 w-14 cursor-grab select-none items-center justify-center rounded-full border-2 border-slate-200 bg-white shadow-lg transition-transform hover:scale-105 active:cursor-grabbing ${
          open ? 'ring-2 ring-slate-900 ring-offset-2' : ''
        }`}
        style={{ right: pos.x, bottom: pos.y }}
        role="button"
        aria-pressed={open}
      >
        <img src={delphiIcon} alt="Delphi" className="h-9 w-9 object-contain" draggable={false} />
      </div>
      {open && (
        <div
          className="pointer-events-auto absolute flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
          style={{ right: pos.x, bottom: pos.y + 68 }}
        >
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 bg-slate-900 px-3 text-white">
            <img src={delphiIcon} alt="" className="h-5 w-5 object-contain" />
            <div className="min-w-0 flex-1 leading-tight">
              <p className="truncate text-sm font-semibold">Delphi</p>
              <p className="truncate text-[11.4px] text-slate-300">over deze werkmap en Apollo</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              title="Gesprek sluiten (Delphi blijft beschikbaar)"
              className="rounded-lg px-2 py-1 text-slate-300 hover:bg-slate-700 hover:text-white"
            >
              ✕
            </button>
          </div>
          <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            {messages.length === 0 && <p className="text-sm leading-relaxed text-slate-500">{INTRO}</p>}
            {messages.map((m) => (
              <div key={m.id} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-slate-900 text-white'
                      : m.refusal
                        ? 'border border-amber-200 bg-amber-50 text-amber-900'
                        : 'bg-slate-100 text-slate-800'
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-400">Delphi denkt na…</div>
              </div>
            )}
            {error && <p className="text-xs text-red-600">{error}</p>}
          </div>
          <div className="flex shrink-0 items-end gap-2 border-t border-slate-200 p-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send()
                }
              }}
              placeholder="Vraag het Delphi…"
              className="max-h-24 min-h-[2.25rem] flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
            />
            <button
              onClick={() => void send()}
              disabled={busy || !input.trim()}
              className="shrink-0 rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-40"
            >
              Verstuur
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
