import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  api,
  type CatalogModel,
  type EmbeddingCatalog,
  type EmbeddingSettings,
  type EmbeddingTest,
  type IndexStatus,
  type PullStatus,
  type ReindexResult,
} from '../api'
import { Badge, Button, Card, ErrorText } from '../components'

const PRESETS = [
  { label: 'OpenAI', url: '' },
  { label: 'Ollama', url: 'http://localhost:11434/v1' },
  { label: 'llama-server', url: 'http://localhost:8080/v1' },
  { label: 'Jina', url: 'https://api.jina.ai/v1' },
  { label: 'Gemini', url: 'https://generativelanguage.googleapis.com/v1beta/openai/' },
]

/** Whether ``url`` already points at that runtime (the backend recognises endpoints the same way). */
function pointsAtRuntime(url: string, runtime: string): boolean {
  const u = url.toLowerCase()
  const ollama = u.includes('11434') || u.includes('ollama')
  return runtime === 'ollama' ? ollama : !ollama && (u.includes('llama') || u.includes(':8080'))
}

const inputCls = 'w-full rounded border border-slate-300 px-2 py-1.5 text-sm'

/** "mock-embedder" is what is left over after leaving the mock provider: not a model of a real one. */
const realModel = (provider: string, model: string) => (provider !== 'mock' && model === 'mock-embedder' ? '' : model)

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export default function EmbeddingsCard() {
  const [saved, setSaved] = useState<EmbeddingSettings | null>(null)
  const [draft, setDraft] = useState<Pick<EmbeddingSettings, 'provider' | 'model' | 'base_url'> | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [clearKey, setClearKey] = useState(false)
  const [status, setStatus] = useState<IndexStatus | null>(null)
  const [catalog, setCatalog] = useState<EmbeddingCatalog | null>(null)
  const [pulls, setPulls] = useState<Record<string, PullStatus>>({})
  const [test, setTest] = useState<EmbeddingTest | null>(null)
  const [reindexResult, setReindexResult] = useState<ReindexResult | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timers = useRef<number[]>([])

  const refresh = useCallback(async (runtime?: string) => {
    const [s, st, cat] = await Promise.all([
      api.getEmbeddingSettings(),
      api.embeddingStatus(),
      api.embeddingCatalog(runtime).catch(() => null),
    ])
    setSaved(s)
    setDraft({ provider: s.provider, model: realModel(s.provider, s.model), base_url: s.base_url })
    setStatus(st)
    setCatalog(cat)
  }, [])

  useEffect(() => {
    refresh().catch((e: Error) => setError(e.message))
    const pending = timers.current
    return () => pending.forEach((t) => window.clearInterval(t))
  }, [refresh])

  if (!saved || !draft) return <Card>{error ? <ErrorText message={error} /> : 'Laden…'}</Card>

  const dirty = draft.provider !== saved.provider || draft.model !== realModel(saved.provider, saved.model) || draft.base_url !== saved.base_url || apiKey !== '' || clearKey
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const save = () =>
    run('save', async () => {
      const body: Parameters<typeof api.updateEmbeddingSettings>[0] = {
        provider: draft.provider,
        model: draft.model.trim(),
        base_url: draft.base_url.trim(),
      }
      if (apiKey) body.api_key = apiKey
      if (clearKey) body.api_key = ''
      await api.updateEmbeddingSettings(body)
      setApiKey('')
      setClearKey(false)
      setTest(null)
      setMessage('Opgeslagen en direct actief.')
      await refresh()
    })

  const pull = (m: CatalogModel) =>
    run(`pull-${m.name}`, async () => {
      const runtime = catalog?.runtime ?? saved.runtime
      let st = await api.startPull(runtime, m.name)
      setPulls((p) => ({ ...p, [m.name]: st }))
      const timer = window.setInterval(async () => {
        st = await api.pullStatus(runtime, m.name).catch(() => st)
        setPulls((p) => ({ ...p, [m.name]: st }))
        if (st.status === 'completed' || st.status === 'failed') {
          window.clearInterval(timer)
          void refresh(runtime).catch(() => undefined)
        }
      }, 1000)
      timers.current.push(timer)
    })

  const real = draft.provider === 'openai'

  return (
    <Card>
      <h2 className="text-lg font-semibold">Embeddingmodel</h2>
      <p className="mt-0.5 text-sm text-slate-500">
        Bepaalt hoe documenten semantisch doorzocht worden. Vectoren van verschillende modellen worden nooit vergeleken:
        na een wissel moeten documenten opnieuw geïndexeerd worden.
      </p>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {(
          [
            { id: 'openai', label: 'OpenAI-compatibel', hint: 'OpenAI, Ollama, llama-server, Jina, Gemini, …' },
            { id: 'mock', label: 'Mock (offline)', hint: 'Hash-gebaseerd, niet semantisch — voor tests' },
          ] as const
        ).map((p) => (
          <button
            key={p.id}
            onClick={() => setDraft({ ...draft, provider: p.id })}
            className={`rounded border px-3 py-2 text-left text-sm ${
              draft.provider === p.id ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'
            }`}
          >
            <span className="block font-medium">{p.label}</span>
            <span className="block text-xs text-slate-500">{p.hint}</span>
          </button>
        ))}
      </div>

      {real && (
        <div className="mt-5 space-y-4">
          <Field label="Base URL" hint="Leeg = api.openai.com. Lokaal model: geen sleutel nodig.">
            <input
              className={inputCls}
              value={draft.base_url}
              onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
              placeholder="https://api.openai.com/v1"
            />
            <span className="mt-1.5 flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => setDraft({ ...draft, base_url: p.url })}
                  className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
                >
                  {p.label}
                </button>
              ))}
            </span>
          </Field>

          <Field label="API-sleutel" hint="Wordt alleen geschreven en nooit teruggetoond. De OpenAI-sleutel gaat alleen naar OpenAI zelf.">
            <span className="flex items-center gap-2">
              <input
                type="password"
                autoComplete="off"
                className={inputCls}
                value={apiKey}
                disabled={clearKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={saved.api_key_set ? '•••••••• (ingesteld — typ om te vervangen)' : 'Nog niet ingesteld'}
              />
              {saved.api_key_set && (
                <label className="flex shrink-0 items-center gap-1 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={clearKey}
                    onChange={(e) => {
                      setClearKey(e.target.checked)
                      if (e.target.checked) setApiKey('')
                    }}
                  />
                  Wissen
                </label>
              )}
            </span>
          </Field>

          {!draft.base_url.trim() && !saved.api_key_set && !apiKey && (
            <p className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              Zonder Base URL en zonder API-sleutel is er geen endpoint om te gebruiken. Vul de Base URL van je lokale
              runtime in (zie de knoppen hierboven) of een sleutel voor OpenAI.
            </p>
          )}

          <Field label="Model" hint="Een model uit de lijst, of elke modelnaam die het endpoint kent. De dimensie wordt vastgelegd en bewaakt.">
            <input
              className={inputCls}
              list="embedding-models"
              value={draft.model}
              onChange={(e) => setDraft({ ...draft, model: e.target.value })}
              placeholder="BAAI/bge-m3"
            />
            <datalist id="embedding-models">
              {(catalog?.models ?? []).map((m) => (
                <option key={m.name} value={m.name}>
                  {m.label}
                </option>
              ))}
            </datalist>
          </Field>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button onClick={() => void save()} disabled={!dirty || busy !== null}>
          {busy === 'save' ? 'Opslaan…' : 'Opslaan'}
        </Button>
        <Button
          variant="secondary"
          disabled={dirty || busy !== null}
          onClick={() => void run('test', async () => setTest(await api.embeddingTest()))}
        >
          {busy === 'test' ? 'Testen…' : 'Testen'}
        </Button>
        {message && !dirty && <span className="text-sm text-emerald-700">{message}</span>}
        {test && (
          <span className={`text-sm ${test.ok ? 'text-emerald-700' : 'text-red-600'}`}>
            {test.ok ? `${test.model}: ${test.dimensions} dimensies, ${test.millis} ms` : test.error}
          </span>
        )}
      </div>
      <ErrorText message={error} />

      {status && (
        <div className="mt-6 rounded border border-slate-200 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-medium">Index</span>{' '}
              <span className="font-mono text-xs text-slate-500">
                {status.model ?? '—'}
                {status.dimensions ? ` · ${status.dimensions} dim` : ''}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                disabled={busy !== null || status.documents_stale === 0}
                onClick={() =>
                  void run('reindex', async () => {
                    setReindexResult(await api.reindex(false))
                    await refresh(catalog?.runtime)
                  })
                }
              >
                {busy === 'reindex' ? 'Bezig…' : `Her-indexeer verouderde (${status.documents_stale})`}
              </Button>
              <Button
                variant="secondary"
                disabled={busy !== null}
                onClick={() =>
                  void run('reindex-all', async () => {
                    setReindexResult(await api.reindex(true))
                    await refresh(catalog?.runtime)
                  })
                }
              >
                Alles opnieuw
              </Button>
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {status.chunks_current} van {status.chunks_total} fragmenten met het actieve model
            {Object.entries(status.by_model)
              .filter(([m]) => m !== status.model)
              .map(([m, n]) => ` · ${n} met ${m === 'legacy' ? 'een oud model (legacy)' : m}`)
              .join('')}
            . {status.documents_stale > 0 && 'Verouderde documenten worden niet doorzocht tot ze opnieuw geïndexeerd zijn.'}
          </p>
          {status.error && <ErrorText message={status.error} />}
          {reindexResult && (
            <p className="mt-2 text-xs text-slate-600">
              {reindexResult.reindexed} van {reindexResult.requested} opnieuw geïndexeerd.
              {reindexResult.failed.length > 0 &&
                ` Mislukt: ${reindexResult.failed.map((f) => `#${f.document_id} (${f.error ?? 'onbekend'})`).join(', ')}`}
            </p>
          )}
        </div>
      )}

      {catalog && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">Lokale modellen</h3>
            <div className="flex gap-1.5">
              {catalog.runtimes.map((r) => (
                <button
                  key={r.id}
                  title={r.available ? r.address : (r.message ?? 'niet bereikbaar')}
                  onClick={() => void run('catalog', async () => {
                    await api.updateEmbeddingSettings({ runtime: r.id as 'ollama' | 'llamacpp' })
                    await refresh(r.id)
                  })}
                  className={`rounded border px-2 py-1 text-xs ${
                    catalog.runtime === r.id ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  {r.label} <span className={r.available ? 'text-emerald-600' : 'text-slate-400'}>●</span>
                </button>
              ))}
            </div>
          </div>
          {catalog.runtimes.find((r) => r.id === catalog.runtime && !r.available) && (
            <p className="mt-1 text-xs text-amber-700">
              {catalog.runtimes.find((r) => r.id === catalog.runtime)?.message ?? 'Runtime niet bereikbaar.'}
            </p>
          )}
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {catalog.models.map((m) => {
              const p = pulls[m.name]
              const running = p && (p.status === 'starting' || p.status === 'downloading')
              return (
                <li key={m.name} className="py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span className="font-medium">{m.label}</span>{' '}
                      <span className="font-mono text-xs text-slate-400">{m.dimension} dim</span>
                      {m.in_use && <span className="ml-2"><Badge kind="ok">in gebruik</Badge></span>}
                      {m.installed && !m.in_use && <span className="ml-2"><Badge kind="neutral">geïnstalleerd</Badge></span>}
                      {m.downloadable && m.official === false && <span className="ml-2"><Badge kind="warn">community-build</Badge></span>}
                      <p className="text-xs text-slate-500">{m.note}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {!m.in_use && (
                        <Button
                          variant="secondary"
                          disabled={busy !== null}
                          onClick={() => {
                            // A local model is only reachable through its runtime: without its address the
                            // endpoint stays empty and the model cannot be used.
                            const base_url = pointsAtRuntime(draft.base_url, catalog.runtime)
                              ? draft.base_url
                              : (catalog.runtimes.find((r) => r.id === catalog.runtime)?.endpoint || draft.base_url)
                            setDraft({ ...draft, provider: 'openai', model: m.name, base_url })
                          }}
                        >
                          Kiezen
                        </Button>
                      )}
                      {m.downloadable ? (
                        <Button variant="secondary" disabled={busy !== null || !!running || m.installed} onClick={() => void pull(m)}>
                          {m.installed ? 'Gedownload' : running ? 'Downloaden…' : 'Downloaden'}
                        </Button>
                      ) : (
                        <span className="text-xs text-slate-400">geen download voor {catalog.runtime}</span>
                      )}
                    </div>
                  </div>
                  {p && p.status !== 'idle' && (
                    <p className={`mt-1 text-xs ${p.status === 'failed' ? 'text-red-600' : 'text-slate-600'}`}>
                      {p.status === 'downloading' && p.percent !== null ? `${p.percent.toFixed(0)}% ` : ''}
                      {p.status}
                      {p.message ? ` — ${p.message}` : ''}
                      {p.reindex_recommended && ' — kies het model, sla op en her-indexeer.'}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Card>
  )
}
