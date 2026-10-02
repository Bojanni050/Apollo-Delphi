import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  api,
  type LLMSettings,
  type LLMStatus,
  type LLMTestResult,
  type LLMTierName,
  type ModelInfo,
  type Provider,
  type TierSettings,
  type TierUpdate,
} from '../api'
import { Badge, Button, Card, ErrorText } from '../components'
import EmbeddingsCard from './EmbeddingsCard'
import AppearanceCard from './AppearanceCard'
import type { Lang } from '../i18n'
import LanguageCard from './LanguageCard'
import ModelPicker from './ModelPicker'
import RetrievalCard from './RetrievalCard'

/**
 * What the provider dropdown offers. ``provider`` is what the backend knows (an OpenAI-compatible endpoint, Anthropic
 * or the offline mock); a preset only fills in the Base URL that goes with it. ``url: null`` = keep what is typed.
 */
const PROVIDER_PRESETS: { id: string; label: string; provider: Provider; url: string | null }[] = [
  { id: 'openai', label: 'OpenAI', provider: 'openai', url: '' },
  { id: 'anthropic', label: 'Anthropic (Claude)', provider: 'anthropic', url: '' },
  { id: 'google', label: 'Google (Gemini)', provider: 'openai', url: 'https://generativelanguage.googleapis.com/v1beta/openai/' },
  { id: 'openrouter', label: 'OpenRouter', provider: 'openai', url: 'https://openrouter.ai/api/v1' },
  { id: 'edenai', label: 'EdenAI', provider: 'openai', url: 'https://api.edenai.run/v3' },
  { id: 'ollama', label: 'Ollama (lokaal)', provider: 'openai', url: 'http://localhost:11434/v1' },
  { id: 'lmstudio', label: 'LM Studio (lokaal)', provider: 'openai', url: 'http://localhost:1234/v1' },
  { id: 'custom', label: 'Andere OpenAI-compatibele server', provider: 'openai', url: null },
  { id: 'mock', label: 'Mock (offline, geen echt model)', provider: 'mock', url: '' },
]

const trimSlash = (url: string) => url.trim().replace(/\/+$/, '').toLowerCase()

/** The preset a provider + Base URL corresponds to; "custom" for an address that is not one of them. */
function presetFor(provider: Provider | '', baseUrl: string): string {
  if (provider === 'mock') return 'mock'
  if (provider === 'anthropic') return 'anthropic'
  const known = PROVIDER_PRESETS.find((p) => p.provider === 'openai' && p.url !== null && trimSlash(p.url) === trimSlash(baseUrl))
  return known ? known.id : 'custom'
}

const TIER_INFO: Record<LLMTierName, { title: string; blurb: string }> = {
  main: {
    title: 'Hoofdmodel',
    blurb: 'Redeneren: onderzoek van issues en het genereren van documenten. Een sterker model is hier nuttig.',
  },
  background: {
    title: 'Achtergrondmodel',
    blurb: 'Bulkwerk over veel documenten: claims uitlezen en Delphi Pulse. Een snel, goedkoop model volstaat.',
  },
}

const inputCls = 'w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-100'

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

type Draft = { provider: Provider | ''; model: string; base_url: string }

/** "mock-model" is what is left over after leaving the mock provider: not a model of a real one, so not shown as one. */
const realModel = (provider: string, model: string) => (provider !== 'mock' && model === 'mock-model' ? '' : model)

function toDraft(t: TierSettings): Draft {
  return { provider: t.provider, model: realModel(t.provider, t.model), base_url: t.base_url }
}

function TierCard({
  tier,
  saved,
  status,
  onSaved,
  onError,
}: {
  tier: LLMTierName
  saved: TierSettings
  status: LLMStatus['tiers'][number] | undefined
  onSaved: () => Promise<void>
  onError: (m: string | null) => void
}) {
  const info = TIER_INFO[tier]
  const isBackground = tier === 'background'
  const [draft, setDraft] = useState<Draft>(toDraft(saved))
  const [apiKey, setApiKey] = useState('')
  const [clearKey, setClearKey] = useState(false)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [modelsNote, setModelsNote] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [result, setResult] = useState<LLMTestResult | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [typeModel, setTypeModel] = useState(false) // type the model name instead of picking it from the list

  // The background tier follows the main tier's provider and endpoint while both are left empty.
  const followsMain = isBackground && draft.provider === '' && draft.base_url === ''
  const effectiveProvider = draft.provider || status?.provider || 'openai'
  const showFields = effectiveProvider !== 'mock'
  const showEndpoint = !followsMain && effectiveProvider === 'openai'

  // Only the newest request may show its answer: a slow one (an unreachable local server) must not overwrite it.
  const latestLoad = useRef(0)
  const loadModels = useCallback(
    async (p: string, baseUrl: string, key = '') => {
      const mine = ++latestLoad.current
      if (!p || p === 'mock') {
        setModels([])
        setModelsNote(null)
        return
      }
      const res = await api.llmModels(tier, p, baseUrl, key)
      if (mine !== latestLoad.current) return
      setModels(res.items.length > 0 ? res.items : res.models.map((id) => ({ id }) as ModelInfo))
      setModelsNote(res.error ?? (res.models.length === 0 ? 'Geen modellen gevonden.' : null))
    },
    [tier],
  )

  useEffect(() => {
    void loadModels(saved.provider || status?.provider || '', saved.base_url || status?.base_url || '').catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const dirty =
    draft.provider !== saved.provider ||
    draft.model !== realModel(saved.provider, saved.model) ||
    draft.base_url !== saved.base_url ||
    apiKey !== '' ||
    clearKey

  const save = async () => {
    setBusy('save')
    onError(null)
    setMessage(null)
    try {
      const body: TierUpdate = { provider: draft.provider, model: draft.model.trim(), base_url: draft.base_url.trim() }
      if (apiKey) body.api_key = apiKey
      if (clearKey) body.api_key = ''
      await api.updateLlmSettings({ [tier]: body })
      setApiKey('')
      setClearKey(false)
      setResult(null)
      setMessage('Opgeslagen en direct actief.')
      await onSaved()
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    setBusy('test')
    try {
      setResult(await api.llmTest(tier))
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const keyHint = isBackground
    ? 'Leeg = sleutel van het hoofdmodel, maar alleen bij hetzelfde endpoint.'
    : 'Wordt alleen geschreven en nooit teruggetoond. Voor een lokaal model niet nodig.'

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{info.title}</h2>
          <p className="mt-0.5 text-sm text-slate-500">{info.blurb}</p>
        </div>
        {status && (
          <Badge kind={status.configured ? 'ok' : 'err'}>{status.configured ? 'ingesteld' : 'niet ingesteld'}</Badge>
        )}
      </div>

      {isBackground && (
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={followsMain}
            onChange={(e) =>
              setDraft(e.target.checked ? { ...draft, provider: '', base_url: '' } : { ...draft, provider: 'openai' })
            }
          />
          Zelfde provider en endpoint als het hoofdmodel
        </label>
      )}

      {!followsMain && (
        <div className="mt-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Provider</span>
            <select
              className={`${inputCls} mt-0.5`}
              value={presetFor(draft.provider, draft.base_url)}
              onChange={(e) => {
                const preset = PROVIDER_PRESETS.find((p) => p.id === e.target.value)
                if (!preset) return
                const base_url = preset.url ?? draft.base_url
                // another provider has other models: do not keep a name that belongs to the previous one
                const same = draft.provider === preset.provider && draft.base_url === base_url
                setDraft({ ...draft, provider: preset.provider, base_url, model: same ? draft.model : '' })
                setTypeModel(false)
                void loadModels(preset.provider, base_url, apiKey).catch(() => undefined)
              }}
            >
              {PROVIDER_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {showFields && (
        <div className="mt-5 space-y-4">
          {showEndpoint && (
            <Field label="Base URL" hint="Wordt ingevuld door de provider hierboven; leeg = api.openai.com. Je kunt het aanpassen.">
              <input
                className={inputCls}
                value={draft.base_url}
                onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
                placeholder="https://api.openai.com/v1"
              />
            </Field>
          )}

          {!followsMain && (
            <Field label="API-sleutel" hint={keyHint}>
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
          )}

          <div>
            <span className="text-sm font-medium text-slate-700">Model</span>
            <div className="mt-0.5">
              {models.length > 0 && !typeModel ? (
                <ModelPicker
                  value={draft.model}
                  models={models}
                  emptyLabel={isBackground ? 'zelfde als hoofdmodel' : '— kies een model —'}
                  onChange={(model) => setDraft({ ...draft, model })}
                />
              ) : (
                <input
                  className={inputCls}
                  value={draft.model}
                  onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                  placeholder={isBackground ? 'zelfde als hoofdmodel' : 'modelnaam'}
                />
              )}
            </div>
            {isBackground && (
              <span className="mt-1 block text-xs text-slate-500">
                Leeg = het model van het hoofdmodel (alleen bij hetzelfde endpoint).
              </span>
            )}
          </div>
          {models.length > 0 && (
            <button type="button" onClick={() => setTypeModel((v) => !v)} className="text-xs text-slate-500 underline hover:text-slate-700">
              {typeModel ? 'Kies uit de lijst' : 'Zelf een modelnaam typen'}
            </button>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              disabled={busy !== null}
              onClick={() => {
                setBusy('models')
                loadModels(effectiveProvider, followsMain ? (status?.base_url ?? '') : draft.base_url, apiKey)
                  .catch((e: Error) => onError(e.message))
                  .finally(() => setBusy(null))
              }}
            >
              {busy === 'models' ? 'Ophalen…' : 'Modellen ophalen'}
            </Button>
            <span className="text-xs text-slate-500">
              {models.length > 0
                ? `${models.length} modellen — kies er een hierboven.`
                : (modelsNote ?? 'Haalt de modellen op met het adres en de sleutel zoals je ze hierboven ziet; opslaan hoeft nog niet.')}
            </span>
          </div>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button onClick={() => void save()} disabled={!dirty || busy !== null}>
          {busy === 'save' ? 'Opslaan…' : 'Opslaan'}
        </Button>
        <Button variant="secondary" disabled={!status?.configured || busy !== null || dirty} onClick={() => void test()}>
          {busy === 'test' ? 'Testen…' : 'Testen'}
        </Button>
        {status && (
          <span className="font-mono text-xs text-slate-500">
            {realModel(status.provider, status.model) || '—'}
            {status.inherits && ' (volgt hoofdmodel)'}
          </span>
        )}
        {message && !dirty && <span className="text-sm text-emerald-700">{message}</span>}
      </div>
      {status?.error &&
        (status.model ? (
          <ErrorText message={status.error} />
        ) : (
          // Nothing is wrong yet: the endpoint is saved, a model is just not chosen. No red error for that.
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
            Nog geen model gekozen. Klik op “Modellen ophalen”, kies er een en sla op.
          </p>
        ))}
      {result && (
        <p className={`mt-3 text-sm ${result.ok ? 'text-emerald-700' : 'text-red-600'}`}>
          {result.ok ? `Antwoord: ${result.reply}` : result.error}
        </p>
      )}
    </Card>
  )
}

export default function SettingsPage({ onChooseLang }: { onChooseLang: (lang: Lang) => void }) {
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [status, setStatus] = useState<LLMStatus | null>(null)
  const [timeout, setTimeoutValue] = useState(120)
  const [savedTimeout, setSavedTimeout] = useState(120)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  const load = useCallback(async () => {
    const [s, st] = await Promise.all([api.getLlmSettings(), api.llmStatus()])
    setSettings(s)
    setStatus(st)
    setTimeoutValue(s.timeout_seconds)
    setSavedTimeout(s.timeout_seconds)
    setVersion((v) => v + 1)
  }, [])

  useEffect(() => {
    load().catch((e: Error) => setError(e.message))
  }, [load])

  if (!settings || !status) {
    return <Card>{error ? <ErrorText message={error} /> : 'Laden…'}</Card>
  }

  const saveTimeout = async () => {
    setError(null)
    try {
      await api.updateLlmSettings({ timeout_seconds: timeout })
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Taalmodellen</h2>
        <p className="mt-1 text-sm text-slate-500">
          Twee niveaus die elk een eigen provider, endpoint, sleutel en model kunnen hebben — bijvoorbeeld een sterk model
          voor redeneren en een snel, goedkoop model voor bulkwerk. Wijzigingen worden in de database bewaard, gelden direct
          en winnen van de omgevingsvariabelen.
        </p>
        <ErrorText message={error} />
      </Card>

      {(['main', 'background'] as const).map((tier) => (
        <TierCard
          key={`${tier}-${version}`}
          tier={tier}
          saved={settings[tier]}
          status={status.tiers.find((t) => t.tier === tier)}
          onSaved={load}
          onError={setError}
        />
      ))}

      <EmbeddingsCard />

      <RetrievalCard />

      <AppearanceCard />
      <LanguageCard onChoose={onChooseLang} />

      <Card>
        <Field label="Time-out (seconden)" hint="Geldt voor beide modellen.">
          <span className="flex items-center gap-3">
            <input
              type="number"
              min={1}
              max={1800}
              className={`${inputCls} max-w-[8rem]`}
              value={timeout}
              onChange={(e) => setTimeoutValue(Number(e.target.value))}
            />
            <Button variant="secondary" disabled={timeout === savedTimeout} onClick={() => void saveTimeout()}>
              Opslaan
            </Button>
          </span>
        </Field>
      </Card>
    </div>
  )
}
