import { useCallback, useEffect, useState } from 'react'
import { api, type PulseItem, type PulseRun } from '../api'
import { Badge, Button, Card, ErrorText, StatusBadge } from '../components'
import Modal from '../components/Modal'
import { useReader } from '../reader'
import { trackPulse, usePulseRunning } from '../pulseActivity'

const RELATION_LABELS: Record<string, string> = {
  'relates-to': 'hangt samen met',
  supports: 'ondersteunt',
  contradicts: 'spreekt tegen',
  extends: 'breidt uit',
}

export default function PulsePage({ workspaceId }: { workspaceId: number | null }) {
  const [run, setRun] = useState<PulseRun | null>(null)
  const [items, setItems] = useState<PulseItem[]>([])
  const busy = usePulseRunning()
  const reader = useReader()
  // "all" decisions ask for a confirmation first: accepting changes the documents' metadata, and neither can be undone at once
  const [confirmAll, setConfirmAll] = useState<'accepted' | 'dismissed' | null>(null)
  const [deciding, setDeciding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // documents that are not through indexing yet: unread ones do not take part, the ones still being embedded do
  const [unread, setUnread] = useState(0)
  const [embedding, setEmbedding] = useState(0)

  useEffect(() => {
    if (workspaceId === null) return
    let cancelled = false
    let timer: number | undefined
    const tick = async () => {
      let waiting = false
      try {
        const docs = await api.listDocuments(workspaceId)
        if (cancelled) return
        const open = docs.filter((d) => d.indexing_status === 'pending' || d.indexing_status === 'processing').length
        const parsed = docs.filter((d) => d.indexing_status === 'parsed').length
        setUnread(open)
        setEmbedding(parsed)
        waiting = open + parsed > 0
      } catch {
        /* the next look tries again */
      }
      if (!cancelled) timer = window.setTimeout(() => void tick(), waiting ? 3000 : 15000)
    }
    void tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [workspaceId])

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
    setError(null)
    try {
      await trackPulse(() => api.runPulse(workspaceId, force))
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const decideAll = async (decision: 'accepted' | 'dismissed') => {
    if (workspaceId === null) return
    setDeciding(true)
    setError(null)
    try {
      await api.decideAllPulse(workspaceId, decision)
      setItems([])
    } catch (e) {
      setError((e as Error).message)
      await load()
    } finally {
      setDeciding(false)
      setConfirmAll(null)
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
        {unread > 0 && (
          <p role="status" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
            {unread} {unread === 1 ? 'document is' : 'documenten zijn'} nog niet gelezen en {unread === 1 ? 'doet' : 'doen'} niet mee. Wacht tot ze
            klaar zijn en draai Delphi Pulse dan opnieuw; wat al is geanalyseerd wordt overgeslagen.
          </p>
        )}
        {unread === 0 && embedding > 0 && (
          <p role="status" className="mt-3 text-xs text-slate-500">
            {embedding} {embedding === 1 ? 'document wordt' : 'documenten worden'} nog geëmbed. Delphi Pulse leest de tekst zelf, dus dat is geen probleem.
          </p>
        )}
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

      {items.length > 0 && (
        <Card className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-slate-600">
            {items.length} {items.length === 1 ? 'voorstel wacht' : 'voorstellen wachten'} op je beslissing. Accepteren verplaatst het bestand naar de voorgestelde map in de git-werkmap en zet het document in de voorgestelde groep. Klik op een voorstel om het document te lezen.
          </p>
          <div className="flex gap-2">
            <Button onClick={() => setConfirmAll('accepted')} disabled={busy || deciding}>
              Alles accepteren
            </Button>
            <Button variant="secondary" onClick={() => setConfirmAll('dismissed')} disabled={busy || deciding}>
              Alles negeren
            </Button>
          </div>
        </Card>
      )}

      {items.map((item) => (
        <Card
          key={item.id}
          className={`cursor-pointer outline-2 outline-slate-400 ${reader.isOpen && reader.target?.documentId === item.document_id ? 'outline' : ''}`}
        >
          <div className="flex items-start justify-between gap-3" onClick={() => reader.open({ documentId: item.document_id })} title="Klik om dit document te lezen">
            <div className="min-w-0">
              <h3 className="truncate font-semibold">{item.filename}</h3>
              {item.summary && <p className="mt-1 text-sm text-slate-600">{item.summary}</p>}
            </div>
            <div className="flex shrink-0 gap-2" onClick={(e) => e.stopPropagation()}>
              <Button onClick={() => void decide(item, 'accepted')}>Accepteren</Button>
              <Button variant="secondary" onClick={() => void decide(item, 'dismissed')}>
                Negeren
              </Button>
            </div>
          </div>
          {(item.folder || item.group) && (
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-slate-600">
              {item.folder && (
                <span className="flex items-center gap-1.5" title="De map in de git-werkmap waar het bestand heen verhuist als je accepteert">
                  Map <Badge kind={item.folder_is_new ? 'warn' : 'neutral'}>{item.folder}/</Badge>
                  {item.folder_is_new && <span className="text-xs text-amber-700">nieuwe map</span>}
                </span>
              )}
              {item.group && (
                <span className="flex items-center gap-1.5" title="De groep (virtuele map in Apollo) waar het document in komt als je accepteert">
                  Groep <Badge kind="neutral">{item.group}</Badge>
                </span>
              )}
            </div>
          )}
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
                  <button
                    type="button"
                    onClick={() => reader.open({ documentId: c.document_id })}
                    title="Lees dit document"
                    className="font-medium underline decoration-slate-300 underline-offset-2 hover:decoration-slate-500"
                  >
                    {c.filename ?? `document ${c.document_id}`}
                  </button>
                  {c.why && <span className="text-slate-500"> — {c.why}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}

      {confirmAll && (
        <Modal
          title={confirmAll === 'accepted' ? `Alle ${items.length} voorstellen accepteren?` : `Alle ${items.length} voorstellen negeren?`}
          onClose={deciding ? undefined : () => setConfirmAll(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirmAll(null)} disabled={deciding}>
                Annuleren
              </Button>
              <Button variant={confirmAll === 'accepted' ? 'primary' : 'danger'} onClick={() => void decideAll(confirmAll)} disabled={deciding}>
                {deciding ? 'Bezig…' : confirmAll === 'accepted' ? 'Alles accepteren' : 'Alles negeren'}
              </Button>
            </>
          }
        >
          <p>
            {confirmAll === 'accepted'
              ? 'De thema’s, verbanden en groepen van alle voorstellen worden in de documenten opgenomen en de bestanden verhuizen naar hun map in de git-werkmap (alles wordt vastgelegd in git). Dat kun je niet in één keer terugdraaien.'
              : 'Alle voorstellen verdwijnen zonder dat er iets in je documenten verandert. Ze komen pas terug als een document verandert of als je “Alles opnieuw” draait.'}
          </p>
        </Modal>
      )}
    </div>
  )
}
