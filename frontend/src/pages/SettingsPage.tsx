import { useEffect, useState } from 'react'
import { api, type LLMStatus, type LLMTestResult } from '../api'
import { Badge, Button, Card, ErrorText } from '../components'

const TIER_LABELS: Record<string, string> = {
  main: 'Hoofdmodel (redeneren, onderzoek, genereren)',
  background: 'Achtergrondmodel (bulk: claims, Pulse)',
}

export default function SettingsPage() {
  const [status, setStatus] = useState<LLMStatus | null>(null)
  const [results, setResults] = useState<Record<string, LLMTestResult>>({})
  const [testing, setTesting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .llmStatus()
      .then(setStatus)
      .catch((e: Error) => setError(e.message))
  }, [])

  const test = async (tier: string) => {
    setTesting(tier)
    try {
      const r = await api.llmTest(tier)
      setResults((prev) => ({ ...prev, [tier]: r }))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTesting(null)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">Taalmodel</h2>
        <p className="mt-1 text-sm text-slate-500">
          Ingesteld via omgevingsvariabelen (<code>LLM_PROVIDER</code>, <code>LLM_MODEL</code>,{' '}
          <code>BACKGROUND_LLM_MODEL</code>, <code>LLM_BASE_URL</code>). Sleutels worden hier nooit getoond.
        </p>
        {status && (
          <p className="mt-3 text-sm">
            Provider: <Badge kind={status.provider === 'mock' ? 'warn' : 'ok'}>{status.provider}</Badge>
            {status.provider === 'mock' && (
              <span className="ml-2 text-slate-500">offline-modus zonder echt model</span>
            )}
            {status.base_url && <span className="ml-2 font-mono text-xs text-slate-500">{status.base_url}</span>}
          </p>
        )}
        <ErrorText message={error} />
      </Card>

      {status?.tiers.map((t) => {
        const r = results[t.tier]
        return (
          <Card key={t.tier}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-semibold">{TIER_LABELS[t.tier] ?? t.tier}</h3>
                <p className="mt-0.5 font-mono text-xs text-slate-500">{t.model}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge kind={t.configured ? 'ok' : 'err'}>{t.configured ? 'ingesteld' : 'niet ingesteld'}</Badge>
                <Button variant="secondary" disabled={!t.configured || testing !== null} onClick={() => void test(t.tier)}>
                  {testing === t.tier ? 'Testen…' : 'Testen'}
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
