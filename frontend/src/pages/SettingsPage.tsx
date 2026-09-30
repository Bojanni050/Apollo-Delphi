import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { api, type LLMSettings, type LLMStatus, type LLMTestResult } from '../api'
import { Badge, Button, Card, ErrorText } from '../components'

const PROVIDERS: { id: LLMSettings['provider']; label: string; hint: string }[] = [
  { id: 'openai', label: 'OpenAI-compatibel', hint: 'OpenAI, Ollama, LM Studio, vLLM, OpenRouter, …' },
  { id: 'anthropic', label: 'Anthropic', hint: 'Claude via de Messages API' },
  { id: 'mock', label: 'Mock (offline)', hint: 'Deterministisch, geen echt model' },
]

const PRESETS = [
  { label: 'OpenAI', url: '' },
  { label: 'Ollama', url: 'http://localhost:11434/v1' },
  { label: 'LM Studio', url: 'http://localhost:1234/v1' },
]

const TIER_LABELS: Record<string, string> = {
  main: 'Hoofdmodel (redeneren, onderzoek, genereren)',
  background: 'Achtergrondmodel (bulk: claims, Pulse)',
}

const inputCls = 'w-full rounded border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100'

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export default function SettingsPage() {
  const [saved, setSaved] = useState<LLMSettings | null>(null)
  const [form, setForm] = useState<LLMSettings | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [clearKey, setClearKey] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [modelsNote, setModelsNote] = useState<string | null>(null)
  const [status, setStatus] = useState<LLMStatus | null>(null)
  const [results, setResults] = useState<Record<string, LLMTestResult>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshStatus = useCallback(async () => {
    setStatus(await api.llmStatus())
  }, [])

  const loadModels = useCallback(async (provider: string, baseUrl: string) => {
    if (provider === 'mock') {
      setModels([])
      setModelsNote(null)
      return
    }
    const res = await api.llmModels(provider, baseUrl)
    setModels(res.models)
    setModelsNote(res.error ?? (res.models.length === 0 ? 'Geen modellen gevonden.' : null))
  }, [])

  useEffect(() => {
    void (async () => {
      try {
        const s = await api.getLlmSettings()
        setSaved(s)
        setForm(s)
        await refreshStatus()
        await loadModels(s.provider, s.base_url)
      } catch (e) {
        setError((e as Error).message)
      }
    })()
  }, [refreshStatus, loadModels])

  if (!form || !saved) {
    return <Card>{error ? <ErrorText message={error} /> : 'Laden…'}</Card>
  }

  const set = <K extends keyof LLMSettings>(key: K, value: LLMSettings[K]) => setForm({ ...form, [key]: value })
  const keySet = form.provider === 'anthropic' ? saved.anthropic_key_set : saved.openai_key_set
  const keyField = form.provider === 'anthropic' ? 'anthropic_api_key' : 'openai_api_key'
  const real = form.provider !== 'mock'
  const dirty =
    JSON.stringify({ ...form, openai_key_set: 0, anthropic_key_set: 0 }) !==
      JSON.stringify({ ...saved, openai_key_set: 0, anthropic_key_set: 0 }) ||
    apiKey !== '' ||
    clearKey

  const save = async () => {
    setBusy('save')
    setError(null)
    setMessage(null)
    try {
      const body: Parameters<typeof api.updateLlmSettings>[0] = {
        provider: form.provider,
        model: form.model.trim(),
        background_model: form.background_model.trim(),
        base_url: form.base_url.trim(),
        timeout_seconds: form.timeout_seconds,
      }
      if (real && apiKey) body[keyField] = apiKey
      if (real && clearKey) body[keyField] = ''
      const s = await api.updateLlmSettings(body)
      setSaved(s)
      setForm(s)
      setApiKey('')
      setClearKey(false)
      setResults({})
      setMessage('Opgeslagen en direct actief.')
      await refreshStatus()
      await loadModels(s.provider, s.base_url)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const test = async (tier: string) => {
    setBusy(`test-${tier}`)
    try {
      const r = await api.llmTest(tier)
      setResults((prev) => ({ ...prev, [tier]: r }))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Taalmodel</h2>
        <p className="mt-1 text-sm text-slate-500">
          Wijzigingen worden in de database bewaard, gelden direct en winnen van de omgevingsvariabelen.
        </p>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                set('provider', p.id)
                setApiKey('')
                setClearKey(false)
                void loadModels(p.id, p.id === 'openai' ? form.base_url : '')
              }}
              className={`rounded border px-3 py-2 text-left text-sm ${
                form.provider === p.id ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'
              }`}
            >
              <span className="block font-medium">{p.label}</span>
              <span className="block text-xs text-slate-500">{p.hint}</span>
            </button>
          ))}
        </div>

        {real && (
          <div className="mt-5 space-y-4">
            {form.provider === 'openai' && (
              <Field label="Base URL" hint="Leeg = api.openai.com. Voor een lokaal model hoeft er geen sleutel bij.">
                <input
                  className={inputCls}
                  value={form.base_url}
                  onChange={(e) => set('base_url', e.target.value)}
                  placeholder="https://api.openai.com/v1"
                />
                <span className="mt-1.5 flex flex-wrap gap-1.5">
                  {PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => set('base_url', p.url)}
                      className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
                    >
                      {p.label}
                    </button>
                  ))}
                </span>
              </Field>
            )}

            <Field
              label="API-sleutel"
              hint="Wordt alleen geschreven en nooit teruggetoond. Sla eerst op; daarna kun je modellen ophalen."
            >
              <span className="flex items-center gap-2">
                <input
                  type="password"
                  autoComplete="off"
                  className={inputCls}
                  value={apiKey}
                  disabled={clearKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={keySet ? '•••••••• (ingesteld — typ om te vervangen)' : 'Nog niet ingesteld'}
                />
                {keySet && (
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

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Hoofdmodel" hint="Voor onderzoek, redeneren en genereren.">
                <input
                  className={inputCls}
                  list="llm-models"
                  value={form.model}
                  onChange={(e) => set('model', e.target.value)}
                />
              </Field>
              <Field label="Achtergrondmodel (optioneel)" hint="Goedkoper model voor bulkwerk; leeg = hoofdmodel.">
                <input
                  className={inputCls}
                  list="llm-models"
                  value={form.background_model}
                  onChange={(e) => set('background_model', e.target.value)}
                />
              </Field>
            </div>
            <datalist id="llm-models">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="secondary"
                disabled={busy !== null}
                onClick={() => {
                  setBusy('models')
                  loadModels(form.provider, form.base_url)
                    .catch((e: Error) => setError(e.message))
                    .finally(() => setBusy(null))
                }}
              >
                {busy === 'models' ? 'Ophalen…' : 'Modellen ophalen'}
              </Button>
              <span className="text-xs text-slate-500">
                {models.length > 0 ? `${models.length} modellen beschikbaar — kies in de velden hierboven.` : modelsNote}
              </span>
            </div>

            <Field label="Time-out (seconden)">
              <input
                type="number"
                min={1}
                max={1800}
                className={`${inputCls} max-w-[8rem]`}
                value={form.timeout_seconds}
                onChange={(e) => set('timeout_seconds', Number(e.target.value))}
              />
            </Field>
          </div>
        )}

        <div className="mt-5 flex items-center gap-3">
          <Button onClick={() => void save()} disabled={!dirty || busy !== null}>
            {busy === 'save' ? 'Opslaan…' : 'Opslaan'}
          </Button>
          {message && !dirty && <span className="text-sm text-emerald-700">{message}</span>}
        </div>
        <ErrorText message={error} />
      </Card>

      {status?.tiers.map((t) => {
        const r = results[t.tier]
        return (
          <Card key={t.tier}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-semibold">{TIER_LABELS[t.tier] ?? t.tier}</h3>
                <p className="mt-0.5 font-mono text-xs text-slate-500">{t.model || '—'}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge kind={t.configured ? 'ok' : 'err'}>{t.configured ? 'ingesteld' : 'niet ingesteld'}</Badge>
                <Button
                  variant="secondary"
                  disabled={!t.configured || busy !== null}
                  onClick={() => void test(t.tier)}
                >
                  {busy === `test-${t.tier}` ? 'Testen…' : 'Testen'}
                </Button>
              </div>
            </div>
            {t.error && <ErrorText message={t.error} />}
            {r && (
              <p className={`mt-3 text-sm ${r.ok ? 'text-emerald-700' : 'text-red-600'}`}>
                {r.ok ? `Antwoord: ${r.reply}` : r.error}
              </p>
            )}
          </Card>
        )
      })}
    </div>
  )
}
