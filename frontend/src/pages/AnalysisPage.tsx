import { useEffect, useState } from 'react'
import { api, type AnalysisRun, type Claim, type Issue } from '../api'
import { Button, Card, ErrorText, StatusBadge } from '../components'

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(res.statusText)
  return res.json() as Promise<T>
}

export default function AnalysisPage({ workspaceId }: { workspaceId?: number | null }) {
  const [run, setRun] = useState<AnalysisRun | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [issues, setIssues] = useState<Issue[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadIssues = async () => {
    const allIssues = await api.listIssues(undefined, workspaceId)
    setIssues(allIssues)
    return allIssues
  }

  useEffect(() => {
    setRun(null)
    setClaims([])
    setIssues([])
    void (async () => {
      try {
        const allIssues = await loadIssues()
        if (allIssues.length > 0) {
          const runId = allIssues[0].analysis_run_id
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
    setBusy(true)
    setError(null)
    try {
      const newRun = await api.runAnalysis(workspaceId)
      setRun(newRun)
      setClaims(await fetchJson<Claim[]>(`/api/analysis/${newRun.id}/claims`))
      await loadIssues()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const contradictions = issues.filter((i) => i.issue_type === 'contradiction')
  const openQuestions = issues.filter((i) => i.issue_type === 'open_question')
  const resolved = issues.filter((i) => i.status === 'resolved')
  const unresolved = issues.filter((i) => i.status !== 'resolved')

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Collection analysis</h2>
          <Button onClick={() => void analyze()} disabled={busy}>
            {busy ? 'Analyzing…' : 'Run analysis'}
          </Button>
        </div>
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
            {issues.map((i) => (
              <li key={i.id} className="border-b last:border-0 pb-2">
                <div className="flex justify-between gap-2">
                  <span>{i.title}</span>
                  <StatusBadge status={i.status} />
                </div>
                <span className="text-xs text-slate-400">{i.issue_type}</span>
              </li>
            ))}
            {issues.length === 0 && <li className="text-slate-400">No issues detected.</li>}
          </ul>
        </Card>
      </div>
    </div>
  )
}
