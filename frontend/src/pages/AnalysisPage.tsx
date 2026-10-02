import { useEffect, useState } from 'react'
import { api, type AnalysisFeedLine, type AnalysisProgress, type AnalysisRun, type Claim, type Issue } from '../api'
import AnalysisLive from '../components/AnalysisLive'
import { Button, Card, ErrorText, StatusBadge } from '../components'

/** The value the API takes for "the documents without a group". */
const NO_GROUP = '__none__'

type GroupChoice = { id: string; label: string; count: number }

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(res.statusText)
  return res.json() as Promise<T>
}

export default function AnalysisPage({ workspaceId }: { workspaceId?: number | null }) {
  const [run, setRun] = useState<AnalysisRun | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [issues, setIssues] = useState<Issue[]>([])
  const [error, setError] = useState<string | null>(null)
  // The analysis that is running (or has just finished) and what it is doing: followed while the page is open
  const [runId, setRunId] = useState<number | null>(null)
  const [progress, setProgress] = useState<AnalysisProgress | null>(null)
  const [feed, setFeed] = useState<AnalysisFeedLine[]>([])
  const busy = runId !== null
  // Analyse everything, or only the documents of the chosen groups (one, two, more): conflicts are then looked for among those
  const [choices, setChoices] = useState<GroupChoice[]>([])
  const [selected, setSelected] = useState<string[]>([])

  const loadIssues = async () => {
    const allIssues = await api.listIssues(undefined, workspaceId)
    setIssues(allIssues)
    return allIssues
  }

  useEffect(() => {
    setRun(null)
    setClaims([])
    setIssues([])
    setChoices([])
    setSelected([])
    setRunId(null)
    setProgress(null)
    setFeed([])
    // an analysis that is already running in this werkmap (started before, on another page): pick it up again
    void api
      .runningAnalysis(workspaceId)
      .then((p) => {
        if (p) setRunId(p.run_id)
      })
      .catch(() => undefined)
    void (async () => {
      try {
        const docs = (await api.listDocuments(workspaceId)).filter((d) => d.indexing_status === 'parsed' || d.indexing_status === 'indexed')
        const counts = new Map<string, number>()
        for (const d of docs) counts.set(d.group_name ?? NO_GROUP, (counts.get(d.group_name ?? NO_GROUP) ?? 0) + 1)
        const names = [...counts.keys()].filter((g) => g !== NO_GROUP).sort((a, b) => a.localeCompare(b, 'nl'))
        if (names.length > 0) {
          setChoices([
            ...names.map((g) => ({ id: g, label: g, count: counts.get(g) ?? 0 })),
            ...(counts.has(NO_GROUP) ? [{ id: NO_GROUP, label: 'Zonder groep', count: counts.get(NO_GROUP) ?? 0 }] : []),
          ])
        }
      } catch {
        // without the list there is just no group choice
      }
    })()
    void (async () => {
      try {
        const allIssues = await loadIssues()
        let runId: number | null = null
        // De laatste run via de werkmap: zo klopt het ook als die run 0 issues heeft.
        if (workspaceId) {
          try {
            const detail = await fetchJson<{ latest_analysis_run_id: number | null }>(`/api/workspaces/${workspaceId}`)
            runId = detail.latest_analysis_run_id
          } catch {
            // val terug op de nieuwste issue
          }
        }
        if (runId === null && allIssues.length > 0) runId = allIssues[0].analysis_run_id
        if (runId !== null) {
          setRun(await fetchJson<AnalysisRun>(`/api/analysis/${runId}`))
          setClaims(await fetchJson<Claim[]>(`/api/analysis/${runId}/claims`))
        }
      } catch {
        // no analysis yet
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId])

  const analyze = async () => {
    setError(null)
    setProgress(null)
    setFeed([])
    try {
      const started = await api.startAnalysis(workspaceId, selected)
      setRunId(started.id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // follow the run: every second what it is doing and the new lines of the feed, until it is finished
  useEffect(() => {
    if (runId === null) return
    let cancelled = false
    let timer: number | undefined
    let since = 0
    const tick = async () => {
      try {
        const p = await api.analysisProgress(runId, since)
        if (cancelled) return
        since = p.last
        setProgress(p)
        if (p.feed.length > 0) setFeed((cur) => [...cur, ...p.feed].slice(-300))
        if (p.finished) {
          if (p.stage === 'mislukt') setError(p.error ?? 'De analyse is mislukt')
          else {
            const finished = await fetchJson<AnalysisRun>(`/api/analysis/${runId}`)
            setRun(finished)
            setClaims(await fetchJson<Claim[]>(`/api/analysis/${runId}/claims`))
            await loadIssues()
          }
          if (!cancelled) setRunId(null)
          return
        }
      } catch {
        /* a hiccup: look again */
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

  const toggle = (id: string) => setSelected((cur) => (cur.includes(id) ? cur.filter((g) => g !== id) : [...cur, id]))
  const chosenDocs = selected.length === 0 ? null : choices.filter((c) => selected.includes(c.id)).reduce((n, c) => n + c.count, 0)

  const contradictions = issues.filter((i) => i.issue_type === 'contradiction' && (!run || i.analysis_run_id === run.id))
  const openQuestions = issues.filter((i) => i.issue_type === 'open_question' && (!run || i.analysis_run_id === run.id))
  const runIssues = run ? issues.filter((i) => i.analysis_run_id === run.id) : issues
  const resolved = runIssues.filter((i) => i.status === 'resolved')
  const unresolved = runIssues.filter((i) => i.status !== 'resolved')

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Collection analysis</h2>
          <Button onClick={() => void analyze()} disabled={busy}>
            {busy ? 'Bezig…' : 'Run analysis'}
          </Button>
        </div>
        {choices.length > 0 && (
          <div className="mb-4">
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Groepen om te analyseren">
              <span className="text-sm text-slate-600">Analyseer</span>
              <button
                type="button"
                onClick={() => setSelected([])}
                disabled={busy}
                aria-pressed={selected.length === 0}
                className={`rounded-full border px-3 py-1 text-sm ${
                  selected.length === 0 ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                Alles
              </button>
              {choices.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggle(c.id)}
                  disabled={busy}
                  aria-pressed={selected.includes(c.id)}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    selected.includes(c.id) ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {c.label} ({c.count})
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-slate-500">
              {chosenDocs === null
                ? 'Alle documenten van de werkmap. Kies een of meer groepen om een onderwerp (of twee) apart te analyseren: tegenstrijdigheden worden dan alleen tussen de gekozen documenten gezocht.'
                : `${chosenDocs} ${chosenDocs === 1 ? 'document' : 'documenten'} in ${selected.length} ${selected.length === 1 ? 'groep' : 'groepen'}: tegenstrijdigheden worden alleen daartussen gezocht.`}
            </p>
          </div>
        )}
        {run && run.stats && run.stats.groups && run.stats.groups.length > 0 && (
          <p className="mb-2 text-xs text-slate-500">
            Laatste analyse beperkt tot: {run.stats.groups.map((g) => (g === NO_GROUP ? 'zonder groep' : g)).join(', ')}
          </p>
        )}
        {run && run.stats && (
          <div className="grid grid-cols-4 gap-3 text-center">
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-2xl font-semibold">{run.stats.documents_analyzed}</div>
              <div className="text-xs text-slate-500">documents</div>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-2xl font-semibold">{run.stats.claims}</div>
              <div className="text-xs text-slate-500">claims</div>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-2xl font-semibold">{run.stats.open_questions}</div>
              <div className="text-xs text-slate-500">open questions</div>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="text-2xl font-semibold">{run.stats.contradictions}</div>
              <div className="text-xs text-slate-500">contradictions</div>
            </div>
          </div>
        )}
        {!run && <p className="text-sm text-slate-400">No analysis yet. Index documents, then run an analysis.</p>}
        <ErrorText message={error} />
      </Card>

      {progress && <AnalysisLive progress={progress} feed={feed} />}

      <div className="grid grid-cols-2 gap-6">
        <Card>
          <h3 className="font-semibold mb-2">Claims ({claims.length})</h3>
          <ul className="space-y-2 text-sm max-h-96 overflow-auto">
            {claims.map((c) => (
              <li key={c.id} className="border-b last:border-0 pb-2">
                <div className="flex justify-between gap-2">
                  <span>{c.statement}</span>
                  <StatusBadge status={c.status} />
                </div>
                <span className="text-xs text-slate-400">document #{c.document_id} · confidence {c.confidence.toFixed(2)}</span>
              </li>
            ))}
            {claims.length === 0 && <li className="text-slate-400">No claims extracted.</li>}
          </ul>
        </Card>
        <Card>
          <h3 className="font-semibold mb-2">Issues</h3>
          <div className="grid grid-cols-2 gap-3 text-center text-sm mb-4">
            <div className="bg-amber-50 rounded-lg p-2">{contradictions.length} contradictions</div>
            <div className="bg-sky-50 rounded-lg p-2">{openQuestions.length} open questions</div>
            <div className="bg-emerald-50 rounded-lg p-2">{resolved.length} resolved</div>
            <div className="bg-slate-50 rounded-lg p-2">{unresolved.length} unresolved</div>
          </div>
          <ul className="space-y-2 text-sm max-h-72 overflow-auto">
            {runIssues.map((i) => (
              <li key={i.id} className="border-b last:border-0 pb-2">
                <div className="flex justify-between gap-2">
                  <span>{i.title}</span>
                  <StatusBadge status={i.status} />
                </div>
                <span className="text-xs text-slate-400">{i.issue_type}</span>
              </li>
            ))}
            {runIssues.length === 0 && <li className="text-slate-400">No issues detected.</li>}
          </ul>
        </Card>
      </div>
    </div>
  )
}
