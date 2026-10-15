import { useEffect, useMemo, useState } from 'react'
import { api, type CheckedClaim, type CodecheckFeedLine, type CodecheckProgress, type CodecheckResult, type DocumentRecord } from '../api'
import { Badge, Button, Card, ErrorText } from '../components'
import { useReader } from '../reader'

/** Hooguit zoveel repositories per check (zelfde grens als de backend). */
const MAX_REPOS = 4

/** Hooguit zoveel documenten per check ("een paar", ook een kostengrens). */
const MAX_DOCUMENTS = 10

const VERDICT_BADGE = { bevestigd: 'ok', tegengesproken: 'err', niet_gevonden: 'warn' } as const

const STAGE_LABELS: Record<string, string> = {
  start: 'Starten…',
  lezen: 'Documenten en code lezen',
  toetsen: 'Beweringen toetsen aan de code',
  klaar: 'Klaar',
  mislukt: 'Mislukt',
}

const time = (iso: string) => new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`).toLocaleTimeString('nl-NL')

function ClaimCard({ claim }: { claim: CheckedClaim }) {
  const reader = useReader()
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 font-medium text-slate-800">{claim.statement}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge kind={VERDICT_BADGE[claim.verdict]}>{claim.verdict.replace('_', ' ')}</Badge>
          <Badge kind="neutral">
            {claim.method === 'llm' ? 'model' : 'offline'} · {(claim.confidence * 100).toFixed(0)}%
          </Badge>
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        {claim.filename} · “{claim.quote.slice(0, 160)}{claim.quote.length > 160 ? '…' : ''}”
      </p>
      {claim.reasoning && <p className="mt-2 text-sm text-slate-600">{claim.reasoning}</p>}
      {claim.evidence.length > 0 && (
        <div className="mt-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Codebewijs ({claim.evidence.length})
          </h4>
          <ul className="space-y-2">
            {claim.evidence.map((e, i) => (
              <li key={`${e.repo}${e.path}${i}`} className="rounded-lg border border-slate-200 p-3 text-sm">
                <p className="text-xs text-slate-500">
                  <span className="font-medium text-slate-700">{e.repo}</span> · {e.path}
                </p>
                <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-slate-600">{e.snippet}</pre>
              </li>
            ))}
          </ul>
        </div>
      )}
      <button
        onClick={() => reader.open({ documentId: claim.document_id, excerpt: claim.quote })}
        className="mt-2 text-xs text-slate-500 underline hover:text-slate-800"
      >
        Lees in het leesvenster
      </button>
    </Card>
  )
}

/** Wat de codecheck nu doet: de fase, waar hij is, de tellers en de tot nu gevonden oordelen (klikbaar). */
function CodecheckLive({ progress, feed }: { progress: CodecheckProgress; feed: CodecheckFeedLine[] }) {
  const percent =
    progress.documents_total > 0 ? Math.min(100, Math.round((progress.documents_done / progress.documents_total) * 100)) : 0
  // Alleen de stappen en de gelezen documenten; een gevonden oordeel staat al als kaart verderop.
  const activity = feed.filter((l) => l.kind !== 'claim').slice(-8)
  return (
    <div aria-live="polite">
      <Card className="border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 font-semibold">
            <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" aria-hidden="true" />
            {STAGE_LABELS[progress.stage] ?? progress.stage}
          </h3>
          <span className="text-xs text-slate-500">gestart om {time(progress.started_at)}</span>
        </div>

        {progress.documents_total > 0 && (
          <>
            <div
              className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
            >
              <div className="h-full rounded-full bg-slate-900 transition-all" style={{ width: `${percent}%` }} />
            </div>
            <p className="mt-1.5 text-sm text-slate-600">
              {progress.current_document ? (
                <>
                  Nu: <span className="font-medium">{progress.current_document}</span> ·{' '}
                </>
              ) : null}
              document {Math.min(progress.documents_done + (progress.current_document ? 1 : 0), progress.documents_total)} van{' '}
              {progress.documents_total}
            </p>
          </>
        )}

        <div className="mt-3 grid grid-cols-4 gap-3 text-center text-sm">
          <div className="rounded-lg bg-slate-50 p-2">{progress.checked} getoetst</div>
          <div className="rounded-lg bg-emerald-50 p-2">{progress.bevestigd} bevestigd</div>
          <div className="rounded-lg bg-red-50 p-2">{progress.tegengesproken} tegengesproken</div>
          <div className="rounded-lg bg-amber-50 p-2">{progress.niet_gevonden} niet gevonden</div>
        </div>

        {progress.error && <p className="mt-3 text-sm text-red-600">{progress.error}</p>}

        {activity.length > 0 && (
          <ul className="mt-3 max-h-32 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 text-sm text-slate-600">
            {activity.map((line) => (
              <li key={line.n} className="flex items-start gap-2" title={time(line.at)}>
                <span className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-slate-400" aria-hidden="true" />
                <span className="min-w-0 break-words">{line.text}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

export default function CodecheckPage({ workspaceId }: { workspaceId: number | null }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [docIds, setDocIds] = useState<number[]>([])
  const [repoIds, setRepoIds] = useState<number[]>([])
  const [urls, setUrls] = useState<string[]>([])
  const [urlInput, setUrlInput] = useState('')
  const [result, setResult] = useState<CodecheckResult | null>(null)
  const [filter, setFilter] = useState<'alles' | CheckedClaim['verdict']>('alles')
  const [error, setError] = useState<string | null>(null)
  // De codecheck die loopt (of net klaar is) en wat hij doet: gevolgd zolang de pagina open is.
  const [runId, setRunId] = useState<number | null>(null)
  const [progress, setProgress] = useState<CodecheckProgress | null>(null)
  const [feed, setFeed] = useState<CodecheckFeedLine[]>([])
  const busy = runId !== null

  useEffect(() => {
    setDocuments([])
    setDocIds([])
    setRepoIds([])
    setUrls([])
    setUrlInput('')
    setResult(null)
    setFilter('alles')
    setError(null)
    setRunId(null)
    setProgress(null)
    setFeed([])
    if (workspaceId === null) return
    // Een codecheck die al loopt in deze werkmap (gestart voor een bezoek elders): weer oppakken.
    void api
      .runningCodecheck(workspaceId)
      .then((p) => {
        if (p) setRunId(p.run_id)
      })
      .catch(() => undefined)
    void (async () => {
      try {
        setDocuments(await api.listDocuments(workspaceId))
      } catch (e) {
        setError((e as Error).message)
      }
    })()
  }, [workspaceId])

  // Volg de run: elke seconde wat hij doet en de nieuwe feedregels, tot hij klaar is.
  useEffect(() => {
    if (runId === null) return
    let cancelled = false
    let timer: number | undefined
    let since = 0
    const tick = async () => {
      try {
        const p = await api.codecheckProgress(runId, since)
        if (cancelled) return
        since = p.last
        setProgress(p)
        if (p.feed.length > 0) setFeed((cur) => [...cur, ...p.feed].slice(-200))
        if (p.finished) {
          if (p.stage === 'mislukt') setError(p.error ?? 'De codecheck is mislukt')
          else {
            setResult(p.result)
            setFilter('alles')
          }
          if (!cancelled) setRunId(null)
          return
        }
      } catch {
        /* een hapering: nog eens kijken */
      }
      if (!cancelled) timer = window.setTimeout(() => void tick(), 1000)
    }
    void tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // De vastgelegde gegevens: geüploade documenten (geen repo-digests: die zijn de andere kant van de vergelijking).
  const docChoices = useMemo(() => documents.filter((d) => d.source_type !== 'github'), [documents])
  const importedRepos = useMemo(() => documents.filter((d) => d.source_type === 'github'), [documents])
  const repoCount = repoIds.length + urls.length
  const reposFull = repoCount >= MAX_REPOS

  if (workspaceId === null) return <Card>Kies of maak eerst een werkmap om documenten naast code te leggen.</Card>

  const toggleId = (ids: number[], id: number, limit: number) =>
    ids.includes(id) ? ids.filter((i) => i !== id) : ids.length < limit ? [...ids, id] : ids

  const addUrl = () => {
    const url = urlInput.trim()
    if (!url || urls.includes(url) || reposFull) return
    setUrls((u) => [...u, url])
    setUrlInput('')
  }

  const canRun = docIds.length > 0 && repoCount > 0 && repoCount <= MAX_REPOS && !busy

  const run = async () => {
    if (!canRun) return
    setError(null)
    setResult(null)
    setProgress(null)
    setFeed([])
    try {
      const started = await api.startCodecheck(workspaceId, docIds, [
        ...repoIds.map((document_id) => ({ document_id })),
        ...urls.map((url) => ({ url })),
      ])
      setRunId(started.run_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const live = progress && !progress.finished ? progress : null
  const shown = result?.checked.filter((c) => filter === 'alles' || c.verdict === filter) ?? []
  const s = result?.summary

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Codecheck</h2>
        <p className="mt-1 text-sm text-slate-500">
          Kies een paar documenten en leg ze naast hooguit {MAX_REPOS} repositories: per bewering uit de documenten
          krijg je een oordeel (bevestigd, tegengesproken of niet gevonden) met het codebewijs erbij.
        </p>

        <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-600">
          Documenten ({docIds.length}/{MAX_DOCUMENTS})
        </h3>
        {docChoices.length === 0 && <p className="text-sm text-slate-400">Nog geen geüploade documenten in deze werkmap.</p>}
        <ul className="max-h-48 space-y-1 overflow-y-auto">
          {docChoices.map((d) => (
            <li key={d.id}>
              <label className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={docIds.includes(d.id)}
                  onChange={() => setDocIds((ids) => toggleId(ids, d.id, MAX_DOCUMENTS))}
                  disabled={busy || (!docIds.includes(d.id) && docIds.length >= MAX_DOCUMENTS)}
                />
                <span className="truncate">{d.filename}</span>
              </label>
            </li>
          ))}
        </ul>

        <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-600">
          Repositories ({repoCount}/{MAX_REPOS})
        </h3>
        {importedRepos.length > 0 && <p className="mb-1 text-xs text-slate-400">Al geïmporteerd:</p>}
        <ul className="max-h-32 space-y-1 overflow-y-auto">
          {importedRepos.map((d) => (
            <li key={d.id}>
              <label className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={repoIds.includes(d.id)}
                  onChange={() => setRepoIds((ids) => toggleId(ids, d.id, MAX_REPOS))}
                  disabled={busy || (!repoIds.includes(d.id) && reposFull)}
                />
                <span className="truncate">{d.filename}</span>
                {d.source_url && <span className="truncate text-xs text-slate-400">{d.source_url}</span>}
              </label>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex gap-2">
          <input
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addUrl()}
            placeholder="Of een repository-URL, bijv. https://github.com/owner/repo"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            disabled={reposFull || busy}
          />
          <Button onClick={addUrl} disabled={!urlInput.trim() || reposFull || busy}>
            Toevoegen
          </Button>
        </div>
        {urls.length > 0 && (
          <ul className="mt-2 space-y-1">
            {urls.map((u) => (
              <li key={u} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-2 py-1 text-sm">
                <span className="truncate">{u}</span>
                <button
                  onClick={() => setUrls((cur) => cur.filter((x) => x !== u))}
                  disabled={busy}
                  className="text-xs text-slate-500 underline hover:text-slate-800 disabled:opacity-50"
                >
                  Verwijder
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-4">
          <Button onClick={() => void run()} disabled={!canRun}>
            {busy ? 'Controleren…' : 'Controleren'}
          </Button>
        </div>
        <ErrorText message={error} />
      </Card>

      {live && <CodecheckLive progress={live} feed={feed} />}

      {live && live.results.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-600">Al gevonden ({live.results.length})</h3>
          {live.results.map((c) => (
            <ClaimCard key={`${c.document_id}:${c.statement}`} claim={c} />
          ))}
        </div>
      )}

      {s && (
        <Card>
          <h3 className="font-semibold">Uitslag</h3>
          <p className="mt-1 text-sm text-slate-500">
            {s.claims} {s.claims === 1 ? 'bewering' : 'beweringen'} uit {s.documents} {s.documents === 1 ? 'document' : 'documenten'},
            vergeleken met {s.repos} {s.repos === 1 ? 'repository' : 'repositories'}
            {result?.repos.map((r) => ` · ${r}`).join('') ?? ''}
            {s.truncated ? ' (meer beweringen dan getoetst: alleen de eerste 50)' : ''}
          </p>
          <div className="mt-3 grid grid-cols-3 gap-3 text-center text-sm">
            <div className="rounded-lg bg-emerald-50 p-2">{s.bevestigd} bevestigd</div>
            <div className="rounded-lg bg-red-50 p-2">{s.tegengesproken} tegengesproken</div>
            <div className="rounded-lg bg-amber-50 p-2">{s.niet_gevonden} niet gevonden</div>
          </div>
          {result && result.skipped_documents.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-slate-500">
              {result.skipped_documents.map((d) => (
                <li key={d.document_id}>Overgeslagen: {d.filename} — {d.reason}</li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter op oordeel">
            {(['alles', 'bevestigd', 'tegengesproken', 'niet_gevonden'] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setFilter(v)}
                aria-pressed={filter === v}
                className={`rounded-full border px-3 py-1 text-sm ${
                  filter === v ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {v === 'alles' ? `Alles (${result?.checked.length ?? 0})` : `${v.replace('_', ' ')} (${result?.checked.filter((c) => c.verdict === v).length ?? 0})`}
              </button>
            ))}
          </div>
        </Card>
      )}

      {shown.map((c) => (
        <ClaimCard key={`${c.document_id}:${c.statement}`} claim={c} />
      ))}
    </div>
  )
}
