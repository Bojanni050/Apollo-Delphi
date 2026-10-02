import { useEffect, useState } from 'react'
import { api, type KnowledgeItem } from '../api'
import { Button, Card, ErrorText } from '../components'
import { useT } from '../i18n'

const TYPE_KEYS: Record<string, Parameters<ReturnType<typeof useT>>[0]> = {
  fact: 'knowledge.facts',
  derived_conclusion: 'knowledge.derived',
  assumption: 'knowledge.assumptions',
  decision: 'knowledge.decisions',
  unresolved_question: 'knowledge.unresolvedQuestions',
  resolved_contradiction: 'knowledge.resolvedContradictions',
  remaining_contradiction: 'knowledge.remainingContradictions',
}

const TYPE_ORDER = [
  'fact',
  'derived_conclusion',
  'assumption',
  'decision',
  'resolved_contradiction',
  'unresolved_question',
  'remaining_contradiction',
]

export default function KnowledgePage({ workspaceId }: { workspaceId?: number | null }) {
  const t = useT()
  const [items, setItems] = useState<KnowledgeItem[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setItems(await api.getKnowledge(workspaceId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    setItems([])
    setError(null)
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId])

  const buildFromLatest = async () => {
    setBusy(true)
    setError(null)
    try {
      const issues = await api.listIssues(undefined, workspaceId)
      if (issues.length === 0) {
        setError('No analysis runs found. Run an analysis first.')
        return
      }
      const runId = Math.max(...issues.map((i) => i.analysis_run_id))
      setItems(await api.buildKnowledge(runId))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const grouped = TYPE_ORDER.map((t) => ({
    type: t,
    items: items.filter((i) => i.item_type === t),
  })).filter((g) => g.items.length > 0)

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Knowledge state</h2>
          <Button onClick={() => void buildFromLatest()} disabled={busy}>
            {busy ? 'Building…' : 'Build from latest analysis'}
          </Button>
        </div>
        <ErrorText message={error} />
      </Card>

      {grouped.map((g) => (
        <Card key={g.type}>
          <h3 className="font-semibold mb-3">{t(TYPE_KEYS[g.type] ?? g.type)}</h3>
          <ul className="space-y-2 text-sm">
            {g.items.map((i) => (
              <li key={i.id} className="border-b last:border-0 pb-2">
                <p>{i.statement}</p>
                {i.explanation && <p className="text-slate-500 text-xs mt-0.5">{i.explanation}</p>}
                <p className="text-slate-400 text-xs mt-0.5">
                  {i.provenance} · confidence {i.confidence.toFixed(2)}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      ))}

      {items.length === 0 && (
        <Card>
          <p className="text-slate-400 text-sm">No knowledge state yet. Run an analysis, investigate issues, then build knowledge.</p>
        </Card>
      )}
    </div>
  )
}
