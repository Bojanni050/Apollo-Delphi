import { useEffect, useState } from 'react'
import { api, type RetrievalSettings } from '../api'
import { Button, Card, ErrorText } from '../components'

type Key = keyof RetrievalSettings

const GROUPS: { title: string; blurb: string; fields: { key: Key; label: string; min: number; max: number; hint: string }[] }[] = [
  {
    title: 'Vragen',
    blurb: 'Hoeveel het model te lezen krijgt bij een vraag in de Vragen-pagina.',
    fields: [
      {
        key: 'ask_top_k',
        label: 'Fragmenten per vraag',
        min: 1,
        max: 30,
        hint: 'Meer fragmenten vinden meer, maar kosten tokens en verdunnen het antwoord.',
      },
      {
        key: 'ask_history_turns',
        label: 'Gespreksbeurten als context',
        min: 1,
        max: 10,
        hint: 'Hoeveel eerdere vragen en antwoorden een vervolgvraag meekrijgt. Het blijft context, nooit een bron.',
      },
    ],
  },
  {
    title: 'Zoeken',
    blurb: 'Hoe de zoekfunctie betekenis en woorden combineert (hybride zoeken).',
    fields: [
      { key: 'search_top_k', label: 'Resultaten per zoekopdracht', min: 1, max: 50, hint: 'Standaardaantal als de zoekopdracht er geen opgeeft.' },
      {
        key: 'search_candidate_multiplier',
        label: 'Kandidaten per resultaat',
        min: 1,
        max: 50,
        hint: 'Elke zoekmethode haalt zoveel keer het gewenste aantal op voordat ze worden samengevoegd.',
      },
      {
        key: 'search_rrf_k',
        label: 'RRF-constante',
        min: 1,
        max: 1000,
        hint: 'Hoger maakt het verschil tussen hoge en lage posities kleiner. 60 is de gebruikelijke waarde.',
      },
    ],
  },
]

const inputCls = 'w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-sm'

export default function RetrievalCard() {
  const [saved, setSaved] = useState<RetrievalSettings | null>(null)
  const [draft, setDraft] = useState<Record<Key, string> | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const adopt = (s: RetrievalSettings) => {
    setSaved(s)
    setDraft(Object.fromEntries(Object.entries(s).map(([k, v]) => [k, String(v)])) as Record<Key, string>)
  }

  useEffect(() => {
    api.getRetrievalSettings().then(adopt).catch((e: Error) => setError(e.message))
  }, [])

  if (!saved || !draft) return <Card>{error ? <ErrorText message={error} /> : 'Laden…'}</Card>

  const fields = GROUPS.flatMap((g) => g.fields)
  const invalid = (key: Key) => {
    const f = fields.find((x) => x.key === key)!
    const n = Number(draft[key])
    return draft[key].trim() === '' || !Number.isInteger(n) || n < f.min || n > f.max
  }
  const changed = (Object.keys(saved) as Key[]).filter((k) => Number(draft[k]) !== saved[k])
  const hasInvalid = (Object.keys(saved) as Key[]).some(invalid)

  const save = async () => {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const body: Partial<RetrievalSettings> = {}
      for (const k of changed) body[k] = Number(draft[k])
      adopt(await api.updateRetrievalSettings(body))
      setMessage('Opgeslagen en direct actief.')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold">Vragen en zoeken</h2>
      <p className="mt-1 text-sm text-slate-500">
        Afstemming van het ophalen van fragmenten. Wijzigingen gelden direct en winnen van de omgevingsvariabelen; je hoeft
        niets opnieuw te indexeren.
      </p>

      {GROUPS.map((g) => (
        <div key={g.title} className="mt-5">
          <h3 className="text-sm font-semibold text-slate-700">{g.title}</h3>
          <p className="text-xs text-slate-500">{g.blurb}</p>
          <div className="mt-3 space-y-3">
            {g.fields.map((f) => (
              <label key={f.key} className="block">
                <span className="text-sm text-slate-700">{f.label}</span>
                <span className="mt-1 block">
                  <input
                    type="number"
                    min={f.min}
                    max={f.max}
                    className={`${inputCls} ${invalid(f.key) ? 'border-red-400' : ''}`}
                    value={draft[f.key]}
                    onChange={(e) => {
                      setMessage(null)
                      setDraft({ ...draft, [f.key]: e.target.value })
                    }}
                  />
                  <span className="ml-2 text-xs text-slate-400">
                    {f.min}–{f.max}
                  </span>
                  <span className="mt-1 block max-w-md text-xs text-slate-500">{f.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button onClick={() => void save()} disabled={busy || changed.length === 0 || hasInvalid}>
          {busy ? 'Opslaan…' : 'Opslaan'}
        </Button>
        {changed.length > 0 && !busy && (
          <Button variant="secondary" onClick={() => adopt(saved)}>
            Herstellen
          </Button>
        )}
        {message && changed.length === 0 && <span className="text-sm text-emerald-700">{message}</span>}
      </div>
      <ErrorText message={error} />
    </Card>
  )
}
