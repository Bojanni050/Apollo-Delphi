import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type DocumentText } from '../api'
import { useReader, type ReaderTarget } from '../reader'
import { RichHtml, RichMarkdown } from './RichText'

// The width is kept as a share of the window (not in pixels): it stays 40% when the window is made bigger or smaller, also
// when it only gets its real size after the app started. The key is new: pixel widths saved before must not hide the default.
const SHARE_KEY = 'apollo.reader.share'
/** The page next to the reading pane never gets narrower than this when dragging. */
const MIN_PAGE_WIDTH = 240
/** The reading pane starts at 40% of the window; dragging the edge changes it and is remembered. */
const DEFAULT_SHARE = 0.4
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
          <mark key={i} className={`rounded-lg px-0.5 ${isCurrent ? 'bg-emerald-100 text-slate-900 ring-1 ring-emerald-200' : isFind ? 'bg-amber-100 text-slate-900' : 'bg-amber-50 text-slate-900'}`}>
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
  // null = choose by itself: formatted when you just open a document, the plain text when a place has to be marked
  const [chosenView, setChosenView] = useState<'formatted' | 'text' | null>(null)
  const [wordHtml, setWordHtml] = useState<{ id: number; html: string } | null>(null)
  const [wordError, setWordError] = useState<string | null>(null)
  const [share, setShare] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(SHARE_KEY))
      return saved > 0.1 && saved < 0.9 ? saved : DEFAULT_SHARE
    } catch {
      return DEFAULT_SHARE
    }
  })
  const [viewport, setViewport] = useState(() => window.innerWidth)
  useEffect(() => {
    const onResize = () => setViewport(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const width = Math.max(MIN_WIDTH, Math.round(share * viewport))
  const body = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  // while the edge is dragged the PDF viewer (an iframe) must not catch the mouse, or the page never sees it move or let go
  const [dragActive, setDragActive] = useState(false)

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

  // Markdown, Word and PDF can be shown as they are meant to look; a text file only as text
  const canFormat = doc != null && ['md', 'docx', 'pdf'].includes(doc.file_type)
  const pdfPage = useMemo(() => {
    if (!doc || !target) return null
    const chunk = target.chunkId != null ? doc.chunks.find((c) => c.id === target.chunkId) : undefined
    return target.page ?? chunk?.page_number ?? null
  }, [doc, target])
  const autoView = doc?.file_type === 'pdf' || range == null ? 'formatted' : 'text'
  const view = !canFormat ? 'text' : (chosenView ?? autoView)
  useEffect(() => setChosenView(null), [target?.nonce])

  // the Word document as HTML, when its formatted view is shown
  useEffect(() => {
    if (view !== 'formatted' || doc?.file_type !== 'docx' || wordHtml?.id === doc.id) return
    let cancelled = false
    setWordError(null)
    api
      .documentHtml(doc.id)
      .then((r) => !cancelled && setWordHtml({ id: doc.id, html: r.html }))
      .catch((e: Error) => !cancelled && setWordError(e.message))
    return () => {
      cancelled = true
    }
  }, [view, doc, wordHtml])

  const scrollToLine = useCallback((line: number) => {
    body.current?.querySelector(`[data-line="${line}"]`)?.scrollIntoView({ block: 'center' })
  }, [])

  // go to the place that was asked for, every time it is asked for
  useEffect(() => {
    if (view !== 'text') return
    if (doc && range) scrollToLine(range.start)
    else if (doc) body.current?.scrollTo({ top: 0 })
  }, [doc, range, target?.nonce, scrollToLine, view])

  useEffect(() => setMatchIndex(0), [find])
  useEffect(() => {
    if (current && view === 'text') scrollToLine(current[0])
  }, [current, scrollToLine, view])

  // drag the left edge to resize; remembered
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const pane = body.current?.closest('aside')
      const container = pane?.parentElement
      if (!pane || !container) return
      // the pane's right edge stays where it is (the context column sits to its right), so the width follows the mouse
      const right = pane.getBoundingClientRect().right
      const beside = container.getBoundingClientRect().right - right // what the context column takes
      const px = Math.min(Math.max(right - e.clientX, MIN_WIDTH), container.clientWidth - beside - MIN_PAGE_WIDTH)
      setShare(px / window.innerWidth)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      setDragActive(false)
      document.body.style.userSelect = ''
      try {
        localStorage.setItem(SHARE_KEY, String(share))
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
  }, [share])

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
    <aside
      className="relative flex flex-col border-l border-slate-200 bg-white"
      // keeps its width; only when the page would get too narrow (the context column opened) does it give way, down to its minimum
      style={{ width, minWidth: MIN_WIDTH }}
      aria-label="Leesvenster"
    >
      <div
        role="separator"
        aria-orientation="vertical"
        title="Sleep om de breedte te veranderen"
        onMouseDown={() => {
          dragging.current = true
          setDragActive(true)
          document.body.style.userSelect = 'none'
        }}
        className="group absolute inset-y-0 -left-1.5 z-10 flex w-3 cursor-col-resize items-center justify-center hover:bg-slate-300/40"
      >
        <span className="h-10 w-1 rounded-lg bg-slate-300 group-hover:bg-slate-500" />
      </div>
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 px-4">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold" title={doc?.filename}>
          {doc ? (doc.title || doc.filename) : 'Leesvenster'}
        </h2>
        <button onClick={close} title="Leesvenster sluiten" className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
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
          {canFormat && (
            <div className="flex items-center gap-1" role="group" aria-label="Weergave">
              {(['formatted', 'text'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setChosenView(v)}
                  aria-pressed={view === v}
                  className={`rounded-lg border px-2 py-0.5 text-xs ${
                    view === v ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {v === 'formatted' ? 'Opgemaakt' : 'Tekst'}
                </button>
              ))}
              {view === 'formatted' && (
                <span className="ml-1 text-[11px] text-slate-400">
                  {doc.file_type === 'pdf' ? 'Het originele PDF-bestand.' : 'Zoeken en markeren: in de tekstweergave.'}
                </span>
              )}
            </div>
          )}
          {view === 'text' && (
          <div className="flex items-center gap-1.5">
            <input
              value={find}
              onChange={(e) => setFind(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && matches.length > 0) setMatchIndex((i) => (i + (e.shiftKey ? matches.length - 1 : 1)) % matches.length)
              }}
              placeholder="Zoek in dit document…"
              aria-label="Zoek in dit document"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2 py-1 text-xs"
            />
            {find.trim() && (
              <span className="shrink-0 text-xs text-slate-500">{matches.length === 0 ? '0' : `${(matchIndex % matches.length) + 1}/${matches.length}`}</span>
            )}
            <button
              onClick={() => setMatchIndex((i) => (i + matches.length - 1) % Math.max(1, matches.length))}
              disabled={matches.length < 2}
              title="Vorige"
              className="rounded-lg border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              ▲
            </button>
            <button
              onClick={() => setMatchIndex((i) => (i + 1) % Math.max(1, matches.length))}
              disabled={matches.length < 2}
              title="Volgende"
              className="rounded-lg border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              ▼
            </button>
          </div>
          )}
          {view === 'text' && !range && target && (target.chunkId != null || target.excerpt || target.lineStart != null) && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              De plek waar je voor kwam is in de tekst niet terug te vinden (het document is mogelijk gewijzigd). Het hele document staat hier.
            </p>
          )}
          {view === 'text' && range && (
            <button onClick={() => scrollToLine(range.start)} className="text-xs text-slate-500 underline hover:text-slate-800">
              Naar de markering (regel {range.start}
              {range.end > range.start ? `–${range.end}` : ''})
            </button>
          )}
        </div>
      )}

      <div ref={body} className={`relative min-h-0 flex-1 overflow-y-auto ${view === 'formatted' && doc?.file_type === 'pdf' ? '' : 'py-2'}`}>
        {!target && !loading && (
          <p className="px-4 py-3 text-sm text-slate-400">
            Klik op een document in de lijst, of op een zoekresultaat, bron of bewijs, om het hier in zijn geheel te lezen, met de plek die telt gemarkeerd. Sleep de rand links van dit venster om de breedte te veranderen.
          </p>
        )}
        {loading && <p className="px-4 py-3 text-sm text-slate-400">Laden…</p>}
        {error && <p className="px-4 py-3 text-sm text-red-600">Dit document kan niet worden gelezen: {error}</p>}
        {doc && !loading && !error && view === 'formatted' && doc.file_type === 'md' && <RichMarkdown text={doc.text} />}
        {doc && !loading && !error && view === 'formatted' && doc.file_type === 'docx' && (
          <>
            {wordError && <p className="px-4 py-3 text-sm text-red-600">Opgemaakt tonen lukt niet: {wordError}</p>}
            {!wordError && wordHtml?.id !== doc.id && <p className="px-4 py-3 text-sm text-slate-400">Laden…</p>}
            {!wordError && wordHtml?.id === doc.id && <RichHtml html={wordHtml.html} />}
          </>
        )}
        {doc && !loading && !error && view === 'formatted' && doc.file_type === 'pdf' && (
          <iframe
            key={`${doc.id}-${pdfPage ?? 0}-${target?.nonce}`}
            title={doc.filename}
            src={`${api.documentFileUrl(doc.id)}${pdfPage != null ? `#page=${pdfPage}` : ''}`}
            className="absolute inset-0 h-full w-full border-0 bg-white"
            style={{ pointerEvents: dragActive ? 'none' : 'auto' }}
          />
        )}
        {doc && !loading && !error && view === 'text' && lines.length > 0 && blocks}
        {doc && !loading && !error && view === 'text' && lines.length === 0 && <p className="px-4 py-3 text-sm text-slate-400">Dit document bevat geen tekst.</p>}
      </div>
    </aside>
  )
}
