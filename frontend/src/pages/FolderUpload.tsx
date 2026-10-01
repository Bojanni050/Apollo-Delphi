import { useRef, useState } from 'react'
import { api, type DocumentRecord, type FolderScan } from '../api'
import Modal from '../components/Modal'
import { Button, ErrorText } from '../components'
import FolderPickerModal from './FolderPickerModal'

const SUPPORTED = ['.pdf', '.docx', '.txt', '.md']
/** Folders that hold tooling, dependencies or build output, never documents. Hidden folders (".something") are skipped too. */
const SKIPPED_FOLDERS = new Set(['node_modules', '__pycache__', 'venv', 'dist', 'build', 'target'])

type Source = { kind: 'file'; file: File } | { kind: 'server'; rel: string; hash: string }
/** ``path`` is the document's name: "<folder>/docs/a.md". */
type Item = { path: string; source: Source }
type Skipped = { path: string; reason: string }
type Plan = { name: string; root: string | null; items: Item[]; skipped: Skipped[]; truncated: boolean }
type Outcome = { stored: number; present: number; failed: { path: string; reason: string }[]; stopped: boolean; queued: number }
type Phase = 'idle' | 'scanning' | 'plan' | 'storing' | 'done' | 'error'

/** The plan for a folder chosen with the browser's own folder input: every subfolder is already in the list. */
export function planFromBrowser(files: File[]): Plan {
  const items: Item[] = []
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
    else if (file.size === 0) reason = 'leeg'
    if (reason) skipped.push({ path, reason })
    else items.push({ path, source: { kind: 'file', file } })
  }
  items.sort((a, b) => a.path.localeCompare(b.path, 'nl'))
  return { name: files[0]?.webkitRelativePath.split('/')[0] ?? '', root: null, items, skipped, truncated: false }
}

/** The plan for a folder the backend has read from disk. */
export function planFromScan(scan: FolderScan): Plan {
  return {
    name: scan.name,
    root: scan.root,
    items: scan.files.map((f) => ({ path: `${scan.name}/${f.path}`, source: { kind: 'server', rel: f.path, hash: f.content_hash } })),
    skipped: scan.skipped,
    truncated: scan.truncated,
  }
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
 * Add a whole folder: every file in it and in all its subfolders.
 *
 * The folder is chosen with the app's own dialog and read by the backend from disk (no popup of the browser, which asks
 * "upload N files to this site?" in its own style and place). Where the backend is not on this computer, "via de browser"
 * still works. Each supported file is stored under its path in the folder (two README.md files stay apart, the werkmap keeps
 * the structure); a file already there (same path, same content) is left alone. Storing takes a fraction of a second per
 * file; indexing (embedding) can take seconds per fragment, so it is queued and runs in the background on the server.
 */
export default function FolderUpload({ workspaceId, onChanged }: { workspaceId: number | null; onChanged?: () => void }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [picking, setPicking] = useState(false)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [progress, setProgress] = useState({ done: 0, current: '' })
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [error, setError] = useState<string | null>(null)
  const stop = useRef(false)
  const browserInput = useRef<HTMLInputElement | null>(null)

  // webkitdirectory is not in React's typings: set it on the element itself.
  const attach = (el: HTMLInputElement | null) => {
    browserInput.current = el
    el?.setAttribute('webkitdirectory', '')
    el?.setAttribute('directory', '')
  }

  const close = () => {
    setPhase('idle')
    setPlan(null)
    setOutcome(null)
    setError(null)
  }

  const scan = async (path: string) => {
    setPicking(false)
    setError(null)
    setPhase('scanning')
    try {
      setPlan(planFromScan(await api.scanFolder(path)))
      setPhase('plan')
    } catch (e) {
      setError((e as Error).message)
      setPhase('error')
    }
  }

  const chooseInBrowser = (list: FileList | null) => {
    const files = Array.from(list ?? [])
    if (files.length === 0) return
    setPlan(planFromBrowser(files))
    setPhase('plan')
  }

  const start = async () => {
    if (!plan) return
    setPhase('storing')
    stop.current = false
    const result: Outcome = { stored: 0, present: 0, failed: [], stopped: false, queued: 0 }
    const newIds: number[] = []
    try {
      const existing = new Set((await api.listDocuments(workspaceId)).map((d: DocumentRecord) => `${d.filename}|${d.content_hash}`))
      for (const [i, item] of plan.items.entries()) {
        if (stop.current) {
          result.stopped = true
          break
        }
        setProgress({ done: i, current: item.path })
        try {
          const hash = item.source.kind === 'server' ? item.source.hash : await sha256(item.source.file)
          if (existing.has(`${item.path}|${hash}`)) {
            result.present++
            continue
          }
          const doc =
            item.source.kind === 'server'
              ? await api.importFolderFile(workspaceId, plan.root as string, item.source.rel)
              : await api.uploadDocument(item.source.file, workspaceId, item.path)
          newIds.push(doc.id)
          result.stored++
        } catch (e) {
          result.failed.push({ path: item.path, reason: (e as Error).message })
        }
      }
      setProgress({ done: plan.items.length, current: '' })
      if (newIds.length > 0) result.queued = (await api.queueIndexing(workspaceId, newIds)).added
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setOutcome(result)
      setPhase('done')
      onChanged?.()
    }
  }

  return (
    <div>
      <input type="file" multiple ref={attach} onChange={(e) => { chooseInBrowser(e.target.files); e.target.value = '' }} className="hidden" />
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => setPicking(true)} disabled={phase !== 'idle'}>
          Map toevoegen…
        </Button>
        <button
          type="button"
          onClick={() => browserInput.current?.click()}
          disabled={phase !== 'idle'}
          className="text-xs text-slate-500 underline hover:text-slate-700 disabled:opacity-50"
          title="De browser vraagt dan zelf om bevestiging, in zijn eigen venster"
        >
          of upload via de browser
        </button>
      </div>

      {picking && <FolderPickerModal title="Kies de map met documenten" onSelect={(path) => void scan(path)} onClose={() => setPicking(false)} />}

      {phase === 'scanning' && (
        <Modal title="Map doorzoeken…">
          <p>Alle submappen worden doorlopen en de bestanden gelezen. Een grote map kan even duren.</p>
        </Modal>
      )}

      {phase === 'error' && (
        <Modal
          title="De map kon niet worden gelezen"
          onClose={close}
          footer={
            <Button variant="secondary" onClick={close}>
              Sluiten
            </Button>
          }
        >
          <ErrorText message={error} />
        </Modal>
      )}

      {phase === 'plan' && plan && (
        <Modal
          title={`Map “${plan.name}” toevoegen`}
          onClose={close}
          width="max-w-lg"
          footer={
            <>
              <Button variant="secondary" onClick={close}>
                Annuleren
              </Button>
              <Button onClick={() => void start()} disabled={plan.items.length === 0}>
                Toevoegen ({plan.items.length})
              </Button>
            </>
          }
        >
          <p className="font-medium text-slate-800">{count(plan.items.length, 'bestand wordt', 'bestanden worden')} toegevoegd.</p>
          <p className="mt-1 text-xs text-slate-500">
            Alle submappen zijn meegenomen. Elk bestand wordt bewaard onder zijn pad in de map. Het indexeren loopt daarna op de
            achtergrond; je kunt gewoon verder werken.
            {plan.skipped.length > 0 && ` Overgeslagen: ${reasons(plan.skipped)}.`}
            {plan.truncated && ' De map bevat meer bestanden dan hier staan; kies een kleinere map of voeg de rest later toe.'}
          </p>
          {plan.skipped.length > 0 && (
            <details className="mt-2 text-xs text-slate-500">
              <summary className="cursor-pointer">Toon overgeslagen bestanden</summary>
              <ul className="mt-1 max-h-40 overflow-y-auto">
                {plan.skipped.slice(0, 200).map((s) => (
                  <li key={s.path} className="break-all">
                    {s.path} <span className="text-slate-400">({s.reason})</span>
                  </li>
                ))}
                {plan.skipped.length > 200 && <li>… en nog {plan.skipped.length - 200}</li>}
              </ul>
            </details>
          )}
        </Modal>
      )}

      {phase === 'storing' && plan && (
        <Modal
          title="Bestanden toevoegen…"
          footer={
            <Button variant="secondary" onClick={() => (stop.current = true)}>
              Stoppen na dit bestand
            </Button>
          }
        >
          <div aria-live="polite">
            <p className="text-slate-800">
              {progress.done} van {plan.items.length} bestanden
            </p>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded bg-slate-200">
              <div className="h-full bg-slate-900 transition-all" style={{ width: `${(progress.done / Math.max(1, plan.items.length)) * 100}%` }} />
            </div>
            <p className="mt-1 truncate text-xs text-slate-500">{progress.current}</p>
          </div>
        </Modal>
      )}

      {phase === 'done' && outcome && (
        <Modal
          title={outcome.stopped ? 'Gestopt' : 'Klaar'}
          onClose={close}
          footer={<Button onClick={close}>Sluiten</Button>}
        >
          <p className="text-slate-800">
            {count(outcome.stored, 'bestand toegevoegd', 'bestanden toegevoegd')}
            {outcome.present > 0 && `, ${outcome.present} stonden er al`}
            {outcome.failed.length > 0 && `, ${outcome.failed.length} mislukt`}.
          </p>
          {outcome.queued > 0 && (
            <p className="mt-1 text-xs text-slate-500">
              Het indexeren van {outcome.queued} {outcome.queued === 1 ? 'bestand loopt' : 'bestanden loopt'} op de achtergrond. De voortgang staat op
              de Documents-pagina; tot dan zijn ze nog niet doorzoekbaar.
            </p>
          )}
          <ErrorText message={error} />
          {outcome.failed.length > 0 && (
            <ul className="mt-2 max-h-40 overflow-y-auto text-xs text-red-600">
              {outcome.failed.slice(0, 50).map((f) => (
                <li key={f.path} className="break-all">
                  {f.path}: {f.reason}
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
    </div>
  )
}
