import { useEffect, useMemo, useState } from 'react'
import { api, type CheckedClaim, type CodecheckResult, type DocumentRecord } from '../api'
import { Badge, Button, Card, ErrorText } from '../components'
import { useReader } from '../reader'

/** Hooguit zoveel repositories per check (zelfde grens als de backend). */
const MAX_REPOS = 4

/** Hooguit zoveel documenten per check ("een paar", ook een kostengrens). */
const MAX_DOCUMENTS = 10

const VERDICT_BADGE = { bevestigd: 'ok', tegengesproken: 'err', niet_gevonden: 'warn' } as const

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

export default function CodecheckPage({ workspaceId }: { workspaceId: number | null }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [docIds, setDocIds] = useState<number[]>([])
  const [repoIds, setRepoIds] = useState<number[]>([])
  const [urls, setUrls] = useState<string[]>([])
  const [urlInput, setUrlInput] = useState('')
  const [result, setResult] = useState<CodecheckResult | null>(null)
  const [filter, setFilter] = useState<'alles' | CheckedClaim['verdict']>('alles')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDocuments([])
    setDocIds([])
    setRepoIds([])
    setUrls([])
    setUrlInput('')
    setResult(null)
    setFilter('alles')
    setError(null)
    if (workspaceId === null) return
    void (async () => {
      try {
        setDocuments(await api.listDocuments(workspaceId))
      } catch (e) {
        setError((e as Error).message)
      }
    })()
  }, [workspaceId])

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
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.runCodecheck(workspaceId, docIds, [
        ...repoIds.map((document_id) => ({ document_id })),
        ...urls.map((url) => ({ url })),
      ])
      setResult(res)
      setFilter('alles')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

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
                  disabled={!docIds.includes(d.id) && docIds.length >= MAX_DOCUMENTS}
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
                  disabled={!repoIds.includes(d.id) && reposFull}
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
            disabled={reposFull}
          />
          <Button onClick={addUrl} disabled={!urlInput.trim() || reposFull}>
            Toevoegen
          </Button>
        </div>
        {urls.length > 0 && (
          <ul className="mt-2 space-y-1">
            {urls.map((u) => (
              <li key={u} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-2 py-1 text-sm">
                <span className="truncate">{u}</span>
                <button onClick={() => setUrls((cur) => cur.filter((x) => x !== u))} className="text-xs text-slate-500 underline hover:text-slate-800">
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
