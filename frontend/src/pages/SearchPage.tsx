import { Fragment, useEffect, useState } from 'react'
import { api, formatLines, type SearchHit, type SearchMode } from '../api'
import { Badge, Button, Card, ErrorText } from '../components'
import { useReader } from '../reader'

const MODES: { id: SearchMode; label: string; hint: string }[] = [
  { id: 'hybrid', label: 'Hybride', hint: 'Combineert betekenis en exacte woorden (bedragen, namen, id’s)' },
  { id: 'semantic', label: 'Betekenis', hint: 'Zoekt op wat er bedoeld wordt, ook met andere woorden' },
  { id: 'keyword', label: 'Trefwoorden', hint: 'Zoekt op de woorden zelf' },
]

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** The excerpt with the words of the query marked, so it is clear why a fragment matched. */
function Highlighted({ text, query }: { text: string; query: string }) {
  const words = [...new Set(query.toLowerCase().split(/\s+/).filter((w) => w.length > 2))]
  if (words.length === 0) return <>{text}</>
  const pattern = new RegExp(`(${words.map(escapeRegExp).join('|')})`, 'gi')
  return (
    <>
      {text.split(pattern).map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded-lg bg-amber-100 px-0.5 text-slate-900">
            {part}
          </mark>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  )
}

/** Search the indexed documents of the werkmap: by meaning, by words, or both. */
export default function SearchPage({ workspaceId, workspaceName }: { workspaceId: number | null; workspaceName?: string | null }) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<SearchMode>('hybrid')
  const [results, setResults] = useState<{ query: string; hits: SearchHit[] } | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const reader = useReader()

  // Results belong to one werkmap: switching werkmap starts a clean page.
  useEffect(() => {
    setResults(null)
    setNote(null)
    setError(null)
  }, [workspaceId])

  const run = async () => {
    const q = query.trim()
    if (!q) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.search(q, workspaceId, mode)
      setResults({ query: q, hits: res.results })
      setNote(res.mode !== mode ? 'Het embeddingmodel is niet bereikbaar: er is alleen op trefwoorden gezocht.' : null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Zoeken</h2>
        <p className="mt-1 text-sm text-slate-500">
          {workspaceId !== null
            ? `Zoekt in de geïndexeerde documenten van “${workspaceName ?? 'deze werkmap'}”.`
            : 'Er is geen werkmap gekozen: dit zoekt alleen in documenten die bij geen werkmap horen.'}{' '}
          Een vraag stellen en een antwoord met bronnen krijgen kan bij Vragen.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !busy && void run()}
            placeholder="Bijvoorbeeld: goedgekeurd budget havenrenovatie"
            aria-label="Zoekopdracht"
            autoFocus
            className="min-w-[14rem] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as SearchMode)}
            aria-label="Zoekmethode"
            title={MODES.find((m) => m.id === mode)?.hint}
            className="rounded-lg border border-slate-300 px-2 py-2 text-sm"
          >
            {MODES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <Button onClick={() => void run()} disabled={busy || !query.trim()}>
            {busy ? 'Zoeken…' : 'Zoeken'}
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-slate-400">{MODES.find((m) => m.id === mode)?.hint}</p>
        {note && <p className="mt-2 text-xs text-amber-700">{note}</p>}
        <ErrorText message={error} />
      </Card>

      {results && (
        <Card>
          <h3 className="text-sm font-semibold text-slate-700">
            {results.hits.length === 0 ? 'Geen resultaten' : `${results.hits.length} ${results.hits.length === 1 ? 'resultaat' : 'resultaten'}`} voor “{results.query}”
          </h3>
          {results.hits.length === 0 && (
            <p className="mt-2 text-sm text-slate-500">
              Probeer andere woorden, of een andere zoekmethode. Documenten die nog niet zijn gelezen worden niet doorzocht; die nog worden geëmbed alleen op woorden.
            </p>
          )}
          <ul className="mt-3 space-y-3">
            {results.hits.map((r) => (
              <li key={r.chunk_id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                  <span className="break-all font-medium text-slate-700">{r.document_filename}</span>
                  <span className="flex flex-wrap items-center gap-2">
                    {[r.section, r.page_number ? `pagina ${r.page_number}` : '', formatLines(r.line_start, r.line_end)].filter(Boolean).join(' · ')}
                    <Badge kind={r.match === 'both' ? 'ok' : 'neutral'}>
                      {r.match === 'both' ? 'betekenis + woorden' : r.match === 'keyword' ? 'woorden' : 'betekenis'}
                    </Badge>
                    {r.similarity > 0 && <span title="Hoe dicht het fragment bij de zoekopdracht ligt (0 tot 1)">{r.similarity.toFixed(2)}</span>}
                  </span>
                </div>
                <p className="mt-1.5 line-clamp-4 whitespace-pre-line break-words text-slate-600">
                  <Highlighted text={r.excerpt} query={results.query} />
                </p>
                <button
                  onClick={() => reader.open({ documentId: r.document_id, chunkId: r.chunk_id, excerpt: r.excerpt, query: results.query, page: r.page_number })}
                  className="mt-1.5 text-xs text-slate-500 underline hover:text-slate-800"
                >
                  Lees in het leesvenster
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
