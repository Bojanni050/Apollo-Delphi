import { useCallback, useEffect, useState } from 'react'
import { api, type PulseItem, type PulseRun } from '../api'
import { Badge, Button, Card, ErrorText, StatusBadge } from '../components'

const RELATION_LABELS: Record<string, string> = {
  'relates-to': 'hangt samen met',
  supports: 'ondersteunt',
  contradicts: 'spreekt tegen',
  extends: 'breidt uit',
}

export default function PulsePage({ workspaceId }: { workspaceId: number | null }) {
  const [run, setRun] = useState<PulseRun | null>(null)
  const [items, setItems] = useState<PulseItem[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (workspaceId === null) return
    try {
      const res = await api.getPulse(workspaceId)
      setRun(res.run)
      setItems(res.items)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [workspaceId])

  useEffect(() => {
    setRun(null)
    setItems([])
    setError(null)
    void load()
  }, [load])

  const runPulse = async (force: boolean) => {
    if (workspaceId === null) return
    setBusy(true)
    setError(null)
    try {
      await api.runPulse(workspaceId, force)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const decide = async (item: PulseItem, decision: 'accepted' | 'dismissed') => {
    try {
      await api.decidePulseItem(item.id, decision)
      setItems((prev) => prev.filter((i) => i.id !== item.id))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (workspaceId === null) {
    return <Card>Kies of maak eerst een werkmap.</Card>
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Delphi Pulse</h2>
            <p className="text-sm text-slate-500">
              Thema&apos;s en verbanden tussen de documenten in deze werkmap. Delphi Pulse doet alleen voorstellen; jij beslist.
            </p>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => void runPulse(false)} disabled={busy}>
              {busy ? 'Bezig…' : 'Delphi Pulse draaien'}
            </Button>
            <Button variant="secondary" onClick={() => void runPulse(true)} disabled={busy}>
              Alles opnieuw
            </Button>
          </div>
        </div>
        {run && (
          <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            Laatste run <StatusBadge status={run.status} />
            <span>
              {run.provider}/{run.model}
            </span>
            {run.stats && (
              <span>
                {run.stats.analysed} geanalyseerd, {run.stats.skipped} ongewijzigd overgeslagen
              </span>
            )}
          </p>
        )}
        {run?.error_message && <ErrorText message={run.error_message} />}
        <ErrorText message={error} />
      </Card>

      {items.length === 0 && run && run.status === 'completed' && (
        <Card>
          <p className="text-sm text-slate-500">Geen openstaande voorstellen.</p>
        </Card>
      )}

      {items.map((item) => (
        <Card key={item.id}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate font-semibold">{item.filename}</h3>
              {item.summary && <p className="mt-1 text-sm text-slate-600">{item.summary}</p>}
            </div>
            <div className="flex shrink-0 gap-2">
              <Button onClick={() => void decide(item, 'accepted')}>Accepteren</Button>
              <Button variant="secondary" onClick={() => void decide(item, 'dismissed')}>
                Negeren
              </Button>
            </div>
          </div>
          {item.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {item.tags.map((t) => (
                <Badge key={t} kind="neutral">
                  {t}
                </Badge>
              ))}
            </div>
          )}
          {item.connections.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              {item.connections.map((c) => (
                <li key={c.document_id} className="text-slate-700">
                  <span className="text-slate-500">{RELATION_LABELS[c.relation] ?? c.relation}</span>{' '}
                  <span className="font-medium">{c.filename ?? `document ${c.document_id}`}</span>
                  {c.why && <span className="text-slate-500"> — {c.why}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}
    </div>
  )
}
