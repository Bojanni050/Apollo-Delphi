import { useEffect, useState } from 'react'
import { api, type Issue, type IssueDetail } from '../api'
import { Button, Card, ErrorText, StatusBadge } from '../components'

export default function IssuesPage() {
  const [issues, setIssues] = useState<Issue[]>([])
  const [selected, setSelected] = useState<IssueDetail | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadIssues = async () => {
    const all = await api.listIssues()
    setIssues(all)
    return all
  }

  useEffect(() => {
    void loadIssues().catch((e) => setError((e as Error).message))
  }, [])

  const select = async (id: number) => {
    setError(null)
    try {
      setSelected(await api.getIssue(id))
      setNote('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const investigate = async (id: number) => {
    setBusy(true)
    setError(null)
    try {
      setSelected(await api.investigateIssue(id))
      await loadIssues()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const decide = async (id: number, decision: 'accept' | 'reject' | 'unresolved') => {
    setBusy(true)
    setError(null)
    try {
      await api.resolveIssue(id, decision, note || undefined)
      setSelected(await api.getIssue(id))
      await loadIssues()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid grid-cols-[300px,1fr] gap-6">
      <Card>
        <h2 className="font-semibold mb-3">Issues</h2>
        <ul className="space-y-2 text-sm">
          {issues.map((i) => (
            <li key={i.id}>
              <button
                onClick={() => void select(i.id)}
                className={`w-full text-left p-2 rounded border ${
                  selected?.id === i.id ? 'border-slate-900 bg-slate-50' : 'hover:bg-slate-50'
                }`}
              >
                <div className="flex justify-between items-center gap-2">
                  <span className="font-medium line-clamp-2">{i.title}</span>
                  <StatusBadge status={i.status} />
                </div>
                <span className="text-xs text-slate-400">{i.issue_type}</span>
              </button>
            </li>
          ))}
          {issues.length === 0 && <li className="text-slate-400">No issues. Run an analysis first.</li>}
        </ul>
      </Card>

      <div className="space-y-4">
        {!selected && <Card><p className="text-slate-400 text-sm">Select an issue to inspect it.</p></Card>}
        {selected && (
          <>
            <Card>
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-lg font-semibold">{selected.title}</h2>
                  <p className="text-sm text-slate-500 mt-1">{selected.description}</p>
                </div>
                <StatusBadge status={selected.status} />
              </div>
              <div className="mt-3 flex gap-2">
                <Button onClick={() => void investigate(selected.id)} disabled={busy}>
                  {busy ? 'Investigating…' : 'Investigate'}
                </Button>
              </div>
              <ErrorText message={error} />
            </Card>

            <Card>
              <h3 className="font-semibold mb-2">Conflicting claims</h3>
              <ul className="space-y-2 text-sm">
                {selected.claims.map((c) => (
                  <li key={c.id} className="border-b last:border-0 pb-2">
                    <p>{c.statement}</p>
                    <span className="text-xs text-slate-400">
                      document #{c.document_id} · value {c.value ?? '—'} {c.unit ?? ''} · <StatusBadge status={c.status} />
                    </span>
                  </li>
                ))}
                {selected.claims.length === 0 && <li className="text-slate-400">No linked claims.</li>}
              </ul>
            </Card>

            <Card>
              <h3 className="font-semibold mb-2">Evidence</h3>
              <ul className="space-y-2 text-sm">
                {selected.evidence.map((e) => (
                  <li key={e.id} className="border rounded p-2">
                    <div className="text-xs text-slate-400 mb-1">
                      document #{e.document_id} {e.page_number ? `· page ${e.page_number}` : ''} {e.section ? `· ${e.section}` : ''} · {e.evidence_type}
                    </div>
                    <p className="text-slate-600">{e.original_text}</p>
                  </li>
                ))}
                {selected.evidence.length === 0 && <li className="text-slate-400">No linked evidence.</li>}
              </ul>
            </Card>

            {selected.resolution && (
              <Card>
                <h3 className="font-semibold mb-2">Proposed resolution</h3>
                <p className="text-sm">
                  <span className="font-medium">Conclusion: </span>
                  {selected.resolution.conclusion ?? '—'}
                </p>
                <p className="text-sm mt-1">
                  <span className="font-medium">Reasoning: </span>
                  {selected.resolution.reasoning ?? '—'}
                </p>
                <p className="text-sm mt-1">
                  <span className="font-medium">Status: </span>
                  <StatusBadge status={selected.resolution.status} />
                  <span className="ml-2 text-slate-400">
                    confidence {selected.resolution.confidence.toFixed(2)} · {selected.resolution.explanation_type ?? '—'}
                  </span>
                </p>
                {selected.resolution.unresolved_uncertainty && (
                  <p className="text-sm mt-1 text-amber-700">
                    <span className="font-medium">Unresolved uncertainty: </span>
                    {selected.resolution.unresolved_uncertainty}
                  </p>
                )}
                <div className="mt-3 space-y-2">
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Optional note / additional information"
                    className="w-full border rounded px-2 py-1.5 text-sm"
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <Button onClick={() => void decide(selected.id, 'accept')} disabled={busy}>Accept</Button>
                    <Button variant="secondary" onClick={() => void decide(selected.id, 'reject')} disabled={busy}>Reject</Button>
                    <Button variant="secondary" onClick={() => void decide(selected.id, 'unresolved')} disabled={busy}>
                      Mark unresolved
                    </Button>
                  </div>
                </div>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  )
}
