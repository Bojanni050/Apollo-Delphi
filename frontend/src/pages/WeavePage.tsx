import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { api, type Weave, type WeaveConnection, type WeaveDocument } from '../api'
import { Card, ErrorText } from '../components'
import { GROUPS_CHANGED } from '../pulseActivity'
import { useReader } from '../reader'

const NO_GROUP = '\u0000none'

const RELATIONS: Record<WeaveConnection['relation'], { label: string; color: string }> = {
  'relates-to': { label: 'hangt samen met', color: '#94a3b8' },
  supports: { label: 'ondersteunt', color: '#10b981' },
  contradicts: { label: 'spreekt tegen', color: '#ef4444' },
  extends: { label: 'breidt uit', color: '#3b82f6' },
}

type Point = { x: number; y: number }

/** The last part of a path: "corpus/Gaia/architectuur/README-00.md" is shown as "README-00.md". */
const baseName = (path: string) => path.split('/').pop() || path

/**
 * Delphi Weave: how the documents of the werkmap hang together. Every group is a block with its documents; a line between two
 * documents is a connection that was accepted in Delphi Pulse. Point at a document (or open it) to see its lines and what they
 * mean; click it to read it in the reading pane. What Pulse has only suggested is not in here until it is accepted.
 */
export default function WeavePage({ workspaceId }: { workspaceId: number | null }) {
  const [weave, setWeave] = useState<Weave | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set()) // relations switched off in the legend
  const [hover, setHover] = useState<number | null>(null)
  const [points, setPoints] = useState<Map<number, Point>>(new Map())
  const box = useRef<HTMLDivElement>(null)
  const pills = useRef<Map<number, HTMLElement>>(new Map())
  const reader = useReader()

  const load = useCallback(async () => {
    if (workspaceId === null) return
    try {
      setWeave(await api.weave(workspaceId))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [workspaceId])

  useEffect(() => {
    setWeave(null)
    void load()
  }, [load])
  useEffect(() => {
    window.addEventListener(GROUPS_CHANGED, load)
    return () => window.removeEventListener(GROUPS_CHANGED, load)
  }, [load])

  const docs = useMemo(() => new Map((weave?.documents ?? []).map((d) => [d.id, d])), [weave])
  const connections = useMemo(() => (weave?.connections ?? []).filter((c) => !hidden.has(c.relation)), [weave, hidden])

  // the groups in alphabetical order, the documents without a group last
  const groups = useMemo(() => {
    const by = new Map<string, WeaveDocument[]>()
    for (const d of weave?.documents ?? []) by.set(d.group ?? NO_GROUP, [...(by.get(d.group ?? NO_GROUP) ?? []), d])
    const names = [...by.keys()].filter((g) => g !== NO_GROUP).sort((a, b) => a.localeCompare(b, 'nl'))
    return [...names, ...(by.has(NO_GROUP) ? [NO_GROUP] : [])].map((name) => ({ name, docs: by.get(name) ?? [] }))
  }, [weave])

  const relationCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const c of weave?.connections ?? []) counts[c.relation] = (counts[c.relation] ?? 0) + 1
    return counts
  }, [weave])

  // where the documents are on the page, so that the lines can be drawn between them
  const measure = useCallback(() => {
    const parent = box.current?.getBoundingClientRect()
    if (!parent) return
    const next = new Map<number, Point>()
    pills.current.forEach((el, id) => {
      const r = el.getBoundingClientRect()
      next.set(id, { x: r.left - parent.left + r.width / 2, y: r.top - parent.top + r.height / 2 })
    })
    setPoints(next)
  }, [])
  useLayoutEffect(() => {
    measure()
  }, [measure, weave, hidden])
  useEffect(() => {
    if (!box.current) return
    const observer = new ResizeObserver(measure)
    observer.observe(box.current)
    window.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [measure, weave])

  const reading = reader.isOpen ? (reader.target?.documentId ?? null) : null
  const focus = hover ?? reading
  const focused = focus !== null ? docs.get(focus) : undefined
  const around = useMemo(() => {
    const ids = new Set<number>()
    if (focus === null) return ids
    for (const c of connections) {
      if (c.source === focus) ids.add(c.target)
      if (c.target === focus) ids.add(c.source)
    }
    return ids
  }, [connections, focus])
  const focusLines = connections.filter((c) => c.source === focus || c.target === focus)

  const path = (a: Point, b: Point) => {
    if (Math.abs(a.y - b.y) < 12) return `M ${a.x} ${a.y} Q ${(a.x + b.x) / 2} ${a.y - 36} ${b.x} ${b.y}` // same row: arch over it
    const mid = (a.y + b.y) / 2
    return `M ${a.x} ${a.y} C ${a.x} ${mid}, ${b.x} ${mid}, ${b.x} ${b.y}`
  }

  if (workspaceId === null) return <Card>Kies of maak eerst een werkmap.</Card>

  const groupCount = groups.filter((g) => g.name !== NO_GROUP).length

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Delphi Weave</h2>
        <p className="mt-1 text-sm text-slate-500">
          De groepen van deze werkmap, hun documenten en hoe die aan elkaar verbonden zijn. Dit zijn de verbanden die je bij Delphi Pulse hebt
          geaccepteerd. Wijs een document aan om zijn lijnen te zien; klik erop om het te lezen.
        </p>
        {weave && (
          <p className="mt-2 text-sm text-slate-600">
            {groupCount} {groupCount === 1 ? 'groep' : 'groepen'} · {weave.documents.length} {weave.documents.length === 1 ? 'document' : 'documenten'} ·{' '}
            {weave.connections.length} {weave.connections.length === 1 ? 'verbinding' : 'verbindingen'}
          </p>
        )}
        {weave && weave.connections.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="Soorten verbindingen">
            {(Object.keys(RELATIONS) as WeaveConnection['relation'][]).map((r) => {
              const off = hidden.has(r)
              return (
                <button
                  key={r}
                  type="button"
                  aria-pressed={!off}
                  disabled={!relationCounts[r]}
                  onClick={() =>
                    setHidden((cur) => {
                      const next = new Set(cur)
                      if (next.has(r)) next.delete(r)
                      else next.add(r)
                      return next
                    })
                  }
                  title={off ? 'Toon deze lijnen' : 'Verberg deze lijnen'}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm disabled:opacity-40 ${
                    off ? 'border-slate-200 text-slate-400 line-through' : 'border-slate-300 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <span className="inline-block h-0.5 w-5 rounded" style={{ backgroundColor: RELATIONS[r].color }} />
                  {RELATIONS[r].label} ({relationCounts[r] ?? 0})
                </button>
              )
            })}
          </div>
        )}
        <ErrorText message={error} />
      </Card>

      {weave && weave.documents.length === 0 && (
        <Card>
          <p className="text-sm text-slate-500">Er zijn nog geen documenten. Importeer eerst een map of bestanden.</p>
        </Card>
      )}

      {weave && weave.documents.length > 0 && groupCount === 0 && weave.connections.length === 0 && (
        <Card>
          <p className="text-sm text-slate-500">
            Er zijn nog geen groepen of verbindingen. Draai Delphi Pulse en accepteer de voorstellen: dan verschijnen ze hier.
          </p>
        </Card>
      )}

      {weave && weave.documents.length > 0 && (
        <div ref={box} className="relative">
          <div className="space-y-4">
            {groups.map((g) => {
              const ids = new Set(g.docs.map((d) => d.id))
              const lines = connections.filter((c) => ids.has(c.source) || ids.has(c.target)).length
              return (
                <Card key={g.name} className="!p-4">
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="font-semibold">{g.name === NO_GROUP ? 'Zonder groep' : g.name}</h3>
                    <span className="text-xs text-slate-500">
                      {g.docs.length} {g.docs.length === 1 ? 'document' : 'documenten'} · {lines} {lines === 1 ? 'verbinding' : 'verbindingen'}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {g.docs.map((d) => {
                      const isFocus = focus === d.id
                      const isNear = around.has(d.id)
                      const dimmed = focus !== null && !isFocus && !isNear
                      return (
                        <button
                          key={d.id}
                          type="button"
                          ref={(el) => {
                            if (el) pills.current.set(d.id, el)
                            else pills.current.delete(d.id)
                          }}
                          onMouseEnter={() => setHover(d.id)}
                          onMouseLeave={() => setHover((cur) => (cur === d.id ? null : cur))}
                          onFocus={() => setHover(d.id)}
                          onBlur={() => setHover((cur) => (cur === d.id ? null : cur))}
                          onClick={() => reader.open({ documentId: d.id })}
                          title={[d.filename, d.folder ? `map: ${d.folder}/` : null, d.tags.length ? `thema’s: ${d.tags.join(', ')}` : null]
                            .filter(Boolean)
                            .join('\n')}
                          className={`relative z-10 max-w-full truncate rounded-lg border bg-white px-2.5 py-1 text-sm transition-opacity ${
                            isFocus
                              ? 'border-slate-900 font-medium text-slate-900'
                              : isNear
                                ? 'border-slate-500 text-slate-800'
                                : 'border-slate-200 text-slate-600 hover:border-slate-400'
                          } ${dimmed ? 'opacity-40' : ''}`}
                        >
                          {baseName(d.filename)}
                        </button>
                      )
                    })}
                  </div>
                </Card>
              )
            })}
          </div>

          <svg className="pointer-events-none absolute inset-0 z-[1] h-full w-full" aria-hidden="true">
            {connections.map((c) => {
              const a = points.get(c.source)
              const b = points.get(c.target)
              if (!a || !b) return null
              const on = c.source === focus || c.target === focus
              return (
                <path
                  key={`${c.source}-${c.target}-${c.relation}`}
                  d={path(a, b)}
                  fill="none"
                  stroke={RELATIONS[c.relation].color}
                  strokeWidth={on ? 3 : 1.5}
                  strokeLinecap="round"
                  opacity={focus === null ? 0.55 : on ? 1 : 0.1}
                />
              )
            })}
          </svg>
        </div>
      )}

      {focused && (
        <Card className="sticky bottom-0 !p-4">
          <h3 className="font-semibold">{baseName(focused.filename)}</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {focused.group ? `groep ${focused.group}` : 'zonder groep'}
            {focused.folder ? ` · map ${focused.folder}/` : ''}
            {focused.tags.length > 0 ? ` · ${focused.tags.join(', ')}` : ''}
          </p>
          {focusLines.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">Geen geaccepteerde verbindingen met andere documenten.</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {focusLines.map((c) => {
                const otherId = c.source === focus ? c.target : c.source
                const other = docs.get(otherId)
                return (
                  <li key={`${c.source}-${c.target}-${c.relation}`} className="flex items-baseline gap-2">
                    <span className="inline-block h-0.5 w-4 shrink-0 translate-y-[-3px] rounded" style={{ backgroundColor: RELATIONS[c.relation].color }} />
                    <span className="text-slate-500">{RELATIONS[c.relation].label}</span>
                    <button
                      type="button"
                      onClick={() => reader.open({ documentId: otherId })}
                      className="font-medium underline decoration-slate-300 underline-offset-2 hover:decoration-slate-500"
                    >
                      {other ? baseName(other.filename) : `document ${otherId}`}
                    </button>
                    {c.why && <span className="text-slate-500">— {c.why}</span>}
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      )}
    </div>
  )
}
