import { useEffect, useRef, useState } from 'react'
import { api, type IndexProgress as Progress } from '../api'
import { Button, Card, ErrorText } from '../components'

/** "ongeveer 4 minuten", "ongeveer 40 seconden". */
function duration(seconds: number): string {
  if (seconds < 90) return `ongeveer ${Math.max(5, Math.round(seconds / 5) * 5)} seconden`
  const minutes = Math.round(seconds / 60)
  return minutes < 90 ? `ongeveer ${minutes} minuten` : `ongeveer ${(minutes / 60).toFixed(1).replace('.', ',')} uur`
}

/**
 * The indexing that runs in the background on the server: how far it is, what is being indexed and how long it will take.
 * Also offers to index documents that are still waiting (for example after the app was stopped half way).
 */
export default function IndexProgress({
  workspaceId,
  waiting,
  onProgress,
}: {
  workspaceId: number | null
  /** Documents of this werkmap that are not indexed yet (pending or failed). */
  waiting: number
  /** Called when the numbers change, so the list of documents can refresh. */
  onProgress?: () => void
}) {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const last = useRef<string>('')

  // Look every 2.5 s while something runs, and every 10 s otherwise (another window may have started it).
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const p = await api.indexingProgress()
        if (cancelled) return
        setProgress(p)
        const key = `${p.active}|${p.done}|${p.failed}`
        if (key !== last.current) {
          last.current = key
          onProgress?.()
        }
        timer = window.setTimeout(() => void tick(), p.active ? 2500 : 10000)
      } catch {
        if (!cancelled) timer = window.setTimeout(() => void tick(), 10000)
      }
    }
    void tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const start = async () => {
    setError(null)
    try {
      setProgress(await api.queueIndexing(workspaceId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!progress) return null
  if (!progress.active && progress.total === 0 && waiting === 0) return null

  const finished = progress.done + progress.failed
  const remaining = Math.max(0, progress.total - finished)

  return (
    <Card className="border border-slate-200">
      {progress.active ? (
        <div aria-live="polite">
          <p className="text-sm font-medium text-slate-800">
            Indexeren op de achtergrond: {finished} van {progress.total}
            {progress.failed > 0 && <span className="text-red-600"> ({progress.failed} mislukt)</span>}
          </p>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded bg-slate-200">
            <div className="h-full bg-slate-900 transition-all" style={{ width: `${(finished / Math.max(1, progress.total)) * 100}%` }} />
          </div>
          <p className="mt-1 truncate text-xs text-slate-500">
            {progress.current ? `Nu: ${progress.current}` : 'Even geduld…'}
            {progress.seconds_per_document != null && remaining > 0 && ` · nog ${duration(remaining * progress.seconds_per_document)}`}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">Je kunt gewoon verder werken; documenten zijn doorzoekbaar zodra ze klaar zijn.</p>
        </div>
      ) : progress.total > 0 ? (
        <p className="text-sm text-slate-800">
          Indexeren klaar: {progress.done} van {progress.total}
          {progress.failed > 0 && <span className="text-red-600">, {progress.failed} mislukt</span>}.
        </p>
      ) : null}

      {!progress.active && waiting > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <span className="text-sm text-slate-700">
            {waiting} {waiting === 1 ? 'document wacht' : 'documenten wachten'} op indexering.
          </span>
          <Button variant="secondary" onClick={() => void start()}>
            Nu indexeren
          </Button>
        </div>
      )}

      {progress.errors.length > 0 && (
        <details className="mt-2 text-xs text-red-600">
          <summary className="cursor-pointer">Mislukte documenten</summary>
          <ul className="mt-1 max-h-32 overflow-y-auto">
            {progress.errors.map((e) => (
              <li key={e.document_id} className="break-all">
                {e.filename}: {e.error ?? 'onbekende fout'}
              </li>
            ))}
          </ul>
        </details>
      )}
      <ErrorText message={error} />
    </Card>
  )
}
