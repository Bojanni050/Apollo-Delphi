import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type DocumentText } from '../api'
import { useReader, type ReaderTarget } from '../reader'

const WIDTH_KEY = 'apollo.reader.width'
const DEFAULT_WIDTH = 480
const MIN_WIDTH = 288

type Range = { start: number; end: number }

/** Words of a search query worth marking. */
const queryWords = (query?: string | null) => [...new Set((query ?? '').toLowerCase().split(/\s+/).filter((w) => w.length > 2))]

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * The lines to show as "the place": from the fragment (its lines are in the text answer, for every file type), from lines
 * that were given, from a page, or by finding the quote in the text. null when there is nothing to point at.
 */
function locate(doc: DocumentText, target: ReaderTarget): Range | null {
  const chunk = target.chunkId != null ? doc.chunks.find((c) => c.id === target.chunkId) : undefined
  if (chunk?.line_start != null) return { start: chunk.line_start, end: chunk.line_end ?? chunk.line_start }
  if (target.lineStart != null) return { start: target.lineStart, end: target.lineEnd ?? target.lineStart }
  if (target.excerpt) {
    const found = findQuote(doc.text, target.excerpt)
    if (found) return found
  }
  if (target.page != null) {
    const page = doc.pages.find((p) => p.page_number === target.page)
    if (page) return { start: page.line, end: page.line }
  }
  return null
}

/** Finds a quote in the text while ignoring differences in whitespace; returns the lines it covers. */
function findQuote(text: string, quote: string): Range | null {
  const collapse = (s: string) => s.replace(/\s+/g, ' ').trim()
  const wanted = collapse(quote)
  if (wanted.length < 8) return null
  // the text with whitespace collapsed, remembering where every character came from
  let flat = ''
  const origin: number[] = []
  let previousSpace = true
  for (let i = 0; i < text.length; i++) {
    const space = /\s/.test(text[i])
    if (space && previousSpace) continue
    flat += space ? ' ' : text[i]
    origin.push(i)
    previousSpace = space
  }
  const head = flat.toLowerCase().indexOf(wanted.slice(0, 80).toLowerCase())
  if (head < 0) return null
  const tailAt = wanted.length > 80 ? flat.toLowerCase().indexOf(wanted.slice(-60).toLowerCase(), head) : -1
  const endFlat = tailAt >= 0 ? tailAt + 60 : head + Math.min(wanted.length, 80)
  const lineOf = (offset: number) => text.slice(0, offset).split('\n').length
  return { start: lineOf(origin[head]), end: lineOf(origin[Math.min(endFlat, origin.length) - 1]) }
}

/** The text of a line with the search words and the find term marked. */
function Marked({ text, words, find, current }: { text: string; words: string[]; find: string; current: number | null }) {
  const terms = [find, ...words].filter(Boolean)
  if (terms.length === 0 || text === '') return <>{text || ' '}</>
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi')
  const findLower = find.toLowerCase()
  let nth = -1
  return (
    <>
      {text.split(pattern).map((part, i) => {
        if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>
        const isFind = findLower !== '' && part.toLowerCase() === findLower
        if (isFind) nth++
        const isCurrent = isFind && nth === current
        return (
          <mark key={i} className={`rounded px-0.5 ${isCurrent ? 'bg-emerald-100 text-slate-900 ring-1 ring-emerald-200' : isFind ? 'bg-amber-100 text-slate-900' : 'bg-amber-50 text-slate-900'}`}>
            {part}
          </mark>
        )
      })}
    </>
  )
}

const LINES_PER_BLOCK = 200

/**
 * The reading pane: a document in full, with line numbers, its pages, the place you came for marked and a search of its own.
 * Opened from a search hit, a citation, a piece of evidence or the list of documents (see reader.tsx).
 */
export default function ReadingPane() {
  const { target, close } = useReader()
  const [doc, setDoc] = useState<DocumentText | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [find, setFind] = useState('')
  const [matchIndex, setMatchIndex] = useState(0)
  const [width, setWidth] = useState(() => {
    try {
      return Number(localStorage.getItem(WIDTH_KEY)) || DEFAULT_WIDTH
    } catch {
      return DEFAULT_WIDTH
    }
  })
  const body = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  // load the document when another one is asked for (the same document again does not reload)
  const documentId = target?.documentId
  useEffect(() => {
    if (documentId == null) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setFind('')
    api
      .documentText(documentId)
      .then((d) => !cancelled && setDoc(d))
      .catch((e: Error) => {
        if (!cancelled) {
          setDoc(null)
          setError(e.message)
        }
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [documentId])

  const range = useMemo(() => (doc && target && doc.id === target.documentId ? locate(doc, target) : null), [doc, target])
  const words = useMemo(() => queryWords(target?.query), [target?.query])
  const lines = useMemo(() => (doc ? doc.text.split('\n') : []), [doc])
  const pageAt = useMemo(() => new Map((doc?.pages ?? []).map((p) => [p.line, p.page_number])), [doc])

  // where the find term occurs: [line, nth occurrence on that line]
  const matches = useMemo(() => {
    const term = find.trim().toLowerCase()
    if (!term) return [] as [number, number][]
    const found: [number, number][] = []
    lines.forEach((line, i) => {
      const lower = line.toLowerCase()
      for (let at = lower.indexOf(term), nth = 0; at >= 0; at = lower.indexOf(term, at + term.length), nth++) found.push([i + 1, nth])
    })
    return found
  }, [lines, find])
  const current = matches.length > 0 ? matches[matchIndex % matches.length] : null

  const scrollToLine = useCallback((line: number) => {
    body.current?.querySelector(`[data-line="${line}"]`)?.scrollIntoView({ block: 'center' })
  }, [])

  // go to the place that was asked for, every time it is asked for
  useEffect(() => {
    if (doc && range) scrollToLine(range.start)
    else if (doc) body.current?.scrollTo({ top: 0 })
  }, [doc, range, target?.nonce, scrollToLine])

  useEffect(() => setMatchIndex(0), [find])
  useEffect(() => {
    if (current) scrollToLine(current[0])
  }, [current, scrollToLine])

  // drag the left edge to resize; remembered
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const container = body.current?.closest('aside')?.parentElement
      if (!container) return
      const right = container.getBoundingClientRect().right
      setWidth(Math.min(Math.max(right - e.clientX, MIN_WIDTH), Math.floor(container.clientWidth * 0.7)))
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.userSelect = ''
      try {
        localStorage.setItem(WIDTH_KEY, String(width))
      } catch {
        /* not remembered */
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [width])

  const blocks: ReactNode[] = []
  for (let from = 0; from < lines.length; from += LINES_PER_BLOCK) {
    const rows: ReactNode[] = []
    for (let i = from; i < Math.min(lines.length, from + LINES_PER_BLOCK); i++) {
      const n = i + 1
      const inRange = range != null && n >= range.start && n <= range.end
      const page = pageAt.get(n)
      rows.push(
        <Fragment key={n}>
          {page != null && (
            <div className="my-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-slate-400">
              <span className="h-px flex-1 bg-slate-200" />
              pagina {page}
              <span className="h-px flex-1 bg-slate-200" />
            </div>
          )}
          <div data-line={n} className={`flex gap-3 border-l-2 px-2 ${inRange ? 'border-amber-200 bg-amber-50' : 'border-transparent'}`}>
            <span className="w-9 shrink-0 select-none pt-0.5 text-right text-[11px] leading-5 text-slate-400">{n}</span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-[13px] leading-5">
              <Marked text={lines[i]} words={words} find={find.trim()} current={current && current[0] === n ? current[1] : null} />
            </span>
          </div>
        </Fragment>,
      )
    }
    // content-visibility: the browser skips laying out the blocks that are far off screen
    blocks.push(
      <div key={from} style={{ contentVisibility: 'auto', containIntrinsicSize: `auto ${LINES_PER_BLOCK * 20}px` }}>
        {rows}
      </div>,
    )
  }

  return (
    <aside className="relative flex shrink-0 flex-col border-l border-slate-200 bg-white" style={{ width }} aria-label="Leesvenster">
      <div
        role="separator"
        aria-orientation="vertical"
        title="Sleep om de breedte te veranderen"
        onMouseDown={() => {
          dragging.current = true
          document.body.style.userSelect = 'none'
        }}
        className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize hover:bg-slate-300/40"
      />
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 px-4">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold" title={doc?.filename}>
          {doc ? (doc.title || doc.filename) : 'Leesvenster'}
        </h2>
        <button onClick={close} title="Leesvenster sluiten" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
          ✕
        </button>
      </div>

      {doc && (
        <div className="shrink-0 space-y-2 border-b border-slate-100 px-4 py-2">
          <p className="truncate text-xs text-slate-500" title={doc.filename}>
            {doc.filename} · {doc.file_type.toUpperCase()} · {doc.line_count} regels
            {doc.pages.length > 0 && ` · ${doc.pages.length} pagina’s`}
            {doc.truncated && ' · ingekort'}
          </p>
          <div className="flex items-center gap-1.5">
            <input
              value={find}
              onChange={(e) => setFind(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && matches.length > 0) setMatchIndex((i) => (i + (e.shiftKey ? matches.length - 1 : 1)) % matches.length)
              }}
              placeholder="Zoek in dit document…"
              aria-label="Zoek in dit document"
              className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-xs"
            />
            {find.trim() && (
              <span className="shrink-0 text-xs text-slate-500">{matches.length === 0 ? '0' : `${(matchIndex % matches.length) + 1}/${matches.length}`}</span>
            )}
            <button
              onClick={() => setMatchIndex((i) => (i + matches.length - 1) % Math.max(1, matches.length))}
              disabled={matches.length < 2}
              title="Vorige"
              className="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              ▲
            </button>
            <button
              onClick={() => setMatchIndex((i) => (i + 1) % Math.max(1, matches.length))}
              disabled={matches.length < 2}
              title="Volgende"
              className="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              ▼
            </button>
          </div>
          {!range && target && (target.chunkId != null || target.excerpt || target.lineStart != null) && (
            <p className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              De plek waar je voor kwam is in de tekst niet terug te vinden (het document is mogelijk gewijzigd). Het hele document staat hier.
            </p>
          )}
          {range && (
            <button onClick={() => scrollToLine(range.start)} className="text-xs text-slate-500 underline hover:text-slate-800">
              Naar de markering (regel {range.start}
              {range.end > range.start ? `–${range.end}` : ''})
            </button>
          )}
        </div>
      )}

      <div ref={body} className="min-h-0 flex-1 overflow-y-auto py-2">
        {!target && !loading && (
          <p className="px-4 py-3 text-sm text-slate-400">
            Kies een document, zoekresultaat, bron of bewijs met “Lees” om het hier in zijn geheel te lezen, met de plek die telt gemarkeerd.
          </p>
        )}
        {loading && <p className="px-4 py-3 text-sm text-slate-400">Laden…</p>}
        {error && <p className="px-4 py-3 text-sm text-red-600">Dit document kan niet worden gelezen: {error}</p>}
        {doc && !loading && !error && lines.length > 0 && blocks}
        {doc && !loading && !error && lines.length === 0 && <p className="px-4 py-3 text-sm text-slate-400">Dit document bevat geen tekst.</p>}
      </div>
    </aside>
  )
}
