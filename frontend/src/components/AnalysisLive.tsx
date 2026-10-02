import { useEffect, useRef } from 'react'
import type { AnalysisFeedLine, AnalysisProgress } from '../api'
import { Card } from '../components'

const STAGE_LABELS: Record<string, string> = {
  start: 'Starten…',
  lezen: 'Documenten lezen en claims zoeken',
  opslaan: 'Claims opslaan met hun bewijs',
  vergelijken: 'Claims vergelijken op tegenstrijdigheden',
  klaar: 'Klaar',
  mislukt: 'Mislukt',
}

/** The dot in front of a line in the feed: what kind of finding it is. */
const KIND_STYLE: Record<string, { dot: string; label: string }> = {
  document: { dot: 'bg-slate-400', label: 'document' },
  claim: { dot: 'bg-emerald-500', label: 'claim' },
  question: { dot: 'bg-amber-500', label: 'open vraag' },
  contradiction: { dot: 'bg-red-500', label: 'tegenstrijdigheid' },
  stage: { dot: 'bg-sky-500', label: 'stap' },
}

const time = (iso: string) => new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`).toLocaleTimeString('nl-NL')

/**
 * What the analysis is doing right now: the stage, the document and fragment it is on, how much it has found so far and a
 * running list of the findings, so there is something to see (and to be sure that it has not got stuck) while it works.
 */
export default function AnalysisLive({ progress, feed }: { progress: AnalysisProgress; feed: AnalysisFeedLine[] }) {
  const list = useRef<HTMLUListElement>(null)
  const running = !progress.finished
  const percent = progress.chunks_total > 0 ? Math.min(100, Math.round((progress.chunks_done / progress.chunks_total) * 100)) : progress.finished ? 100 : 0

  // keep the newest line in view while it runs
  useEffect(() => {
    if (running && list.current) list.current.scrollTop = list.current.scrollHeight
  }, [feed, running])

  return (
    <div aria-live="polite">
    <Card className="border-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-semibold">
          {running && <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" aria-hidden="true" />}
          {STAGE_LABELS[progress.stage] ?? progress.stage}
        </h3>
        <span className="text-xs text-slate-500">gestart om {time(progress.started_at)}</span>
      </div>

      {progress.documents_total > 0 && (
        <>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            title={`${progress.chunks_done} van ${progress.chunks_total} fragmenten gelezen`}
          >
            <div className="h-full rounded-full bg-slate-900 transition-all" style={{ width: `${percent}%` }} />
          </div>
          <p className="mt-1.5 text-sm text-slate-600">
            {progress.current_document ? (
              <>
                Nu: <span className="font-medium">{progress.current_document}</span> ·{' '}
              </>
            ) : null}
            document {Math.min(progress.documents_done + (running && progress.current_document ? 1 : 0), progress.documents_total)} van{' '}
            {progress.documents_total} · fragment {progress.chunks_done} van {progress.chunks_total}
          </p>
        </>
      )}

      <div className="mt-3 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-xl font-semibold">{progress.claims}</div>
          <div className="text-xs text-slate-500">claims gevonden</div>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-xl font-semibold">{progress.open_questions}</div>
          <div className="text-xs text-slate-500">open vragen</div>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-xl font-semibold">{progress.contradictions}</div>
          <div className="text-xs text-slate-500">tegenstrijdigheden</div>
        </div>
      </div>

      {progress.error && <p className="mt-3 text-sm text-red-600">{progress.error}</p>}

      {feed.length > 0 && (
        <ul ref={list} className="mt-3 max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2 text-sm" aria-label="Wat er gevonden wordt">
          {feed.map((line) => {
            const style = KIND_STYLE[line.kind] ?? KIND_STYLE.stage
            return (
              <li key={line.n} className="flex items-start gap-2" title={`${style.label} · ${time(line.at)}\n${line.text}`}>
                <span className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${style.dot}`} aria-hidden="true" />
                <span className={`min-w-0 break-words ${line.kind === 'stage' || line.kind === 'document' ? 'font-medium text-slate-700' : 'text-slate-600'}`}>
                  {line.text}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
    </div>
  )
}
