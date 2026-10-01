import { useCallback, useEffect, useRef, useState } from 'react'
import { api, formatLines, type Answer } from '../api'
import { Badge, Button, Card, ErrorText } from '../components'

/** Renders the answer text with each [n] as a button that jumps to its source. */
function AnswerText({ text, onCite }: { text: string; onCite: (n: number) => void }) {
  return (
    <p className="whitespace-pre-wrap leading-relaxed text-slate-800">
      {text.split(/(\[\d+\])/g).map((part, i) => {
        const m = /^\[(\d+)\]$/.exec(part)
        if (!m) return <span key={i}>{part}</span>
        const n = Number(m[1])
        return (
          <button
            key={i}
            onClick={() => onCite(n)}
            className="mx-0.5 rounded bg-slate-200 px-1 align-super text-[10px] font-semibold text-slate-700 hover:bg-slate-900 hover:text-white"
            title={`Naar bron ${n}`}
          >
            {n}
          </button>
        )
      })}
    </p>
  )
}

function AnswerCard({ answer }: { answer: Answer }) {
  const [active, setActive] = useState<number | null>(null)
  const sourceRefs = useRef<Record<number, HTMLLIElement | null>>({})

  const cite = (n: number) => {
    setActive(n)
    sourceRefs.current[n]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  const extractive = answer.model_provider === 'mock'

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-semibold text-slate-900">{answer.question}</h3>
        <div className="flex flex-wrap items-center gap-1.5">
          {!answer.answered && <Badge kind="warn">niet beantwoord</Badge>}
          {answer.answered && answer.grounded && <Badge kind="ok">bronnen gecontroleerd</Badge>}
          {answer.answered && !answer.grounded && <Badge kind="err">controleer zelf</Badge>}
          <Badge kind="neutral">{extractive ? 'extractief (offline)' : answer.model_name || answer.model_provider}</Badge>
        </div>
      </div>

      <div className="mt-3">
        <AnswerText text={answer.answer} onCite={cite} />
      </div>

      {answer.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          {answer.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}

      {answer.citations.length > 0 && (
        <div className="mt-4">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Bronnen ({answer.citations.length} van {answer.sources_considered || answer.citations.length} gelezen)
          </h4>
          <ul className="space-y-2">
            {answer.citations.map((c) => (
              <li
                key={c.n}
                ref={(el) => {
                  sourceRefs.current[c.n] = el
                }}
                className={`rounded border p-3 text-sm ${active === c.n ? 'border-slate-900 bg-slate-50' : 'border-slate-200'}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                  <span>
                    <span className="mr-1 rounded bg-slate-200 px-1 font-semibold text-slate-700">{c.n}</span>
                    <span className="font-medium text-slate-700">{c.document_filename}</span>
                    {c.page_number ? ` · pagina ${c.page_number}` : ''}
                    {c.section ? ` · ${c.section}` : ''}
                    {c.line_start != null ? ` · ${formatLines(c.line_start, c.line_end)}` : ''}
                  </span>
                  <Badge kind={c.match === 'both' ? 'ok' : 'neutral'}>
                    {c.match === 'both' ? 'betekenis + woorden' : c.match === 'keyword' ? 'woorden' : 'betekenis'}
                  </Badge>
                </div>
                <p className="mt-1.5 whitespace-pre-wrap text-slate-600">{c.excerpt}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

export default function AskPage({ workspaceId }: { workspaceId: number | null }) {
  const [question, setQuestion] = useState('')
  const [current, setCurrent] = useState<Answer | null>(null)
  const [history, setHistory] = useState<Answer[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadHistory = useCallback(async () => {
    if (workspaceId === null) return
    try {
      setHistory(await api.askHistory(workspaceId))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [workspaceId])

  useEffect(() => {
    setCurrent(null)
    setHistory([])
    setError(null)
    void loadHistory()
  }, [loadHistory])

  if (workspaceId === null) return <Card>Kies of maak eerst een werkmap om vragen te stellen.</Card>

  const ask = async () => {
    const q = question.trim()
    if (!q) return
    setBusy(true)
    setError(null)
    try {
      const a = await api.ask(q, workspaceId)
      setCurrent(a)
      setQuestion('')
      await loadHistory()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const earlier = history.filter((h) => h.id !== current?.id)

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Vraag stellen</h2>
        <p className="mt-1 text-sm text-slate-500">
          Het antwoord komt uitsluitend uit de documenten van deze werkmap en noemt de fragmenten waarop het steunt.
          Staat het er niet in, dan zegt Apollo dat in plaats van te gokken.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !busy && void ask()}
            placeholder="Bijvoorbeeld: wat is het goedgekeurde budget?"
            className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <Button onClick={() => void ask()} disabled={busy || !question.trim()}>
            {busy ? 'Zoeken…' : 'Vraag stellen'}
          </Button>
        </div>
        <ErrorText message={error} />
      </Card>

      {current && <AnswerCard key={current.id} answer={current} />}

      {earlier.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-600">Eerdere vragen</h3>
          <ul className="space-y-2">
            {earlier.map((h) => (
              <li key={h.id}>
                <button
                  onClick={() => setCurrent(h)}
                  className="w-full rounded border border-slate-200 bg-white px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span className="font-medium text-slate-800">{h.question}</span>
                  <span className="ml-2 text-xs text-slate-400">{new Date(h.created_at).toLocaleString('nl-NL')}</span>
                  {!h.answered && <span className="ml-2 text-xs text-amber-700">niet beantwoord</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
