import { useRef, useState } from 'react'
import { api } from '../api'
import { Button, ErrorText } from '../components'

const SUPPORTED = ['.pdf', '.docx', '.txt', '.md']
/** Folders that hold tooling, dependencies or build output, never documents. Hidden folders (".something") are skipped too. */
const SKIPPED_FOLDERS = new Set(['node_modules', '__pycache__', 'venv', 'dist', 'build', 'target'])

type Candidate = { file: File; path: string }
type Skipped = { path: string; reason: string }
type Plan = { root: string; upload: Candidate[]; skipped: Skipped[] }
type Outcome = { added: number; present: number; failed: { path: string; reason: string }[]; stopped: boolean }

/** Which files of a chosen folder are taken along, and why the others are not. Every subfolder is already in the list. */
export function planFolder(files: File[]): Plan {
  const upload: Candidate[] = []
  const skipped: Skipped[] = []
  for (const file of files) {
    const path = file.webkitRelativePath || file.name
    const parts = path.split('/')
    const name = parts[parts.length - 1]
    const folders = parts.slice(0, -1).slice(1) // the chosen folder itself is the root, not a reason to skip
    const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')).toLowerCase() : ''
    let reason = ''
    if (folders.some((f) => f.startsWith('.') || SKIPPED_FOLDERS.has(f))) reason = 'genegeerde map'
    else if (name.startsWith('.') || name.startsWith('~$')) reason = 'tijdelijk of verborgen bestand'
    else if (!SUPPORTED.includes(ext)) reason = 'niet ondersteund'
    else if (file.size === 0) reason = 'leeg bestand'
    if (reason) skipped.push({ path, reason })
    else upload.push({ file, path })
  }
  upload.sort((a, b) => a.path.localeCompare(b.path, 'nl'))
  return { root: files[0]?.webkitRelativePath.split('/')[0] ?? '', upload, skipped }
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

function reasons(skipped: Skipped[]): string {
  const by = new Map<string, number>()
  for (const s of skipped) by.set(s.reason, (by.get(s.reason) ?? 0) + 1)
  return [...by].map(([reason, n]) => `${n} ${reason}`).join(', ')
}

/**
 * Upload a whole folder: every file in it and in all its subfolders. Each supported file is stored under its path inside
 * the folder (so two README.md files stay apart and the werkmap keeps the structure) and indexed. A file that is already
 * there (same path, same content) is left alone, so choosing the same folder again only adds what is new.
 */
export default function FolderUpload({ workspaceId, onChanged }: { workspaceId: number | null; onChanged?: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState({ done: 0, current: '' })
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [error, setError] = useState<string | null>(null)
  const stop = useRef(false)

  // webkitdirectory is not in React's typings: set it on the element itself.
  const attach = (el: HTMLInputElement | null) => {
    el?.setAttribute('webkitdirectory', '')
    el?.setAttribute('directory', '')
  }

  const choose = (list: FileList | null) => {
    setOutcome(null)
    setError(null)
    const files = Array.from(list ?? [])
    setPlan(files.length > 0 ? planFolder(files) : null)
  }

  const start = async () => {
    if (!plan) return
    setRunning(true)
    setOutcome(null)
    setError(null)
    stop.current = false
    const result: Outcome = { added: 0, present: 0, failed: [], stopped: false }
    try {
      const existing = new Set((await api.listDocuments(workspaceId)).map((d) => `${d.filename}|${d.content_hash}`))
      for (const [i, { file, path }] of plan.upload.entries()) {
        if (stop.current) {
          result.stopped = true
          break
        }
        setProgress({ done: i, current: path })
        try {
          if (existing.has(`${path}|${await sha256(file)}`)) {
            result.present++
            continue
          }
          const doc = await api.uploadDocument(file, workspaceId, path)
          const indexed = await api.indexDocument(doc.id)
          if (indexed.indexing_status === 'indexed') result.added++
          else result.failed.push({ path, reason: indexed.error_message ?? 'indexeren mislukt' })
        } catch (e) {
          result.failed.push({ path, reason: (e as Error).message })
        }
      }
      setProgress({ done: plan.upload.length, current: '' })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setOutcome(result)
      setPlan(null)
      setRunning(false)
      onChanged?.()
    }
  }

  return (
    <div>
      <input id="folder-upload" type="file" multiple ref={attach} onChange={(e) => { choose(e.target.files); e.target.value = '' }} className="hidden" />
      {!plan && !running && (
        <Button variant="secondary" onClick={() => document.getElementById('folder-upload')?.click()}>
          Map uploaden…
        </Button>
      )}

      {plan && !running && (
        <div className="rounded border border-slate-200 p-3 text-sm">
          <p className="font-medium text-slate-800">
            Map “{plan.root}”: {count(plan.upload.length, 'bestand wordt', 'bestanden worden')} toegevoegd
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            Alle submappen zijn meegenomen. Elk bestand wordt bewaard onder zijn pad in de map en geïndexeerd.
            {plan.skipped.length > 0 && ` Overgeslagen: ${reasons(plan.skipped)}.`}
          </p>
          {plan.skipped.length > 0 && (
            <details className="mt-1 text-xs text-slate-500">
              <summary className="cursor-pointer">Toon overgeslagen bestanden</summary>
              <ul className="mt-1 max-h-32 overflow-y-auto">
                {plan.skipped.slice(0, 200).map((s) => (
                  <li key={s.path} className="break-all">
                    {s.path} <span className="text-slate-400">({s.reason})</span>
                  </li>
                ))}
                {plan.skipped.length > 200 && <li>… en nog {plan.skipped.length - 200}</li>}
              </ul>
            </details>
          )}
          <div className="mt-3 flex gap-2">
            <Button onClick={() => void start()} disabled={plan.upload.length === 0}>
              Uploaden en indexeren ({plan.upload.length})
            </Button>
            <Button variant="secondary" onClick={() => setPlan(null)}>
              Annuleren
            </Button>
          </div>
        </div>
      )}

      {running && plan && (
        <div className="rounded border border-slate-200 p-3 text-sm" aria-live="polite">
          <p className="text-slate-800">
            {progress.done} van {plan.upload.length} bestanden
          </p>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded bg-slate-200">
            <div className="h-full bg-slate-900 transition-all" style={{ width: `${(progress.done / Math.max(1, plan.upload.length)) * 100}%` }} />
          </div>
          <p className="mt-1 truncate text-xs text-slate-500">{progress.current}</p>
          <div className="mt-2">
            <Button variant="secondary" onClick={() => (stop.current = true)}>
              Stoppen na dit bestand
            </Button>
          </div>
        </div>
      )}

      {outcome && !running && (
        <div className="rounded border border-slate-200 p-3 text-sm">
          <p className="text-slate-800">
            {outcome.stopped ? 'Gestopt. ' : ''}
            {count(outcome.added, 'bestand toegevoegd', 'bestanden toegevoegd')}
            {outcome.present > 0 && `, ${outcome.present} stonden er al`}
            {outcome.failed.length > 0 && `, ${outcome.failed.length} mislukt`}.
          </p>
          {outcome.failed.length > 0 && (
            <ul className="mt-1 max-h-32 overflow-y-auto text-xs text-red-600">
              {outcome.failed.slice(0, 50).map((f) => (
                <li key={f.path} className="break-all">
                  {f.path}: {f.reason}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2">
            <Button variant="secondary" onClick={() => setOutcome(null)}>
              Sluiten
            </Button>
          </div>
        </div>
      )}
      <ErrorText message={error} />
    </div>
  )
}
