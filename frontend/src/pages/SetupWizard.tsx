/**
 * First-run setup, shown while there is no werkmap yet: name it, choose where it lives, optionally add the
 * first documents.
 *
 * The werkmap is created at the end of step 2 (name and folder go to the API in one call, which also sets up
 * its git repository). The parent is told only when the whole flow is finished: handing it the werkmap earlier
 * would fill its list, and the app would replace this wizard before step 3 could be seen.
 *
 * Paths are validated by the backend, not here: the form sends what was typed and shows the server's message.
 */
import { useEffect, useRef, useState } from 'react'
import { api, type Workspace } from '../api'
import { Button, Card, ErrorText } from '../components'
import FolderPickerModal from './FolderPickerModal'
import FolderUpload from './FolderUpload'

type Step = 'name' | 'folder' | 'documents'

export type AfterSetup = 'documents' | 'settings'

const inputCls = 'w-full rounded border border-slate-300 px-3 py-2 text-sm'

const STEPS: { id: Step; label: string }[] = [
  { id: 'name', label: 'Naam' },
  { id: 'folder', label: 'Map' },
  { id: 'documents', label: 'Documenten' },
]

function Progress({ step }: { step: Step }) {
  const at = STEPS.findIndex((s) => s.id === step)
  return (
    <ol className="mb-5 flex items-center gap-2 text-xs">
      {STEPS.map((s, i) => (
        <li key={s.id} className="flex items-center gap-2">
          <span
            className={`flex h-5 w-5 items-center justify-center rounded-full font-semibold ${
              i < at ? 'bg-emerald-600 text-white' : i === at ? 'bg-slate-900 text-white' : 'bg-slate-200 text-slate-500'
            }`}
          >
            {i < at ? '✓' : i + 1}
          </span>
          <span className={i === at ? 'font-medium text-slate-900' : 'text-slate-500'}>{s.label}</span>
          {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-slate-300" />}
        </li>
      ))}
    </ol>
  )
}

type Upload = { id: number; name: string; state: 'bezig' | 'klaar' | 'mislukt'; detail?: string }

export default function SetupWizard({
  onFinished,
  onSkip,
}: {
  /** Called once the whole flow is done; the app selects the werkmap and opens ``after``. */
  onFinished: (workspace: Workspace, after: AfterSetup) => void | Promise<void>
  onSkip: () => void
}) {
  const [step, setStep] = useState<Step>('name')
  const [name, setName] = useState('')
  const [folder, setFolder] = useState('')
  const [picking, setPicking] = useState(false)
  const [created, setCreated] = useState<Workspace | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploads, setUploads] = useState<Upload[]>([])
  const [offlineModels, setOfflineModels] = useState<string[]>([])
  const fileInput = useRef<HTMLInputElement>(null)
  const nextUploadId = useRef(0)

  // Step 3 only: are the models still the offline mock ones? Then answers and search are not real yet.
  useEffect(() => {
    if (step !== 'documents') return
    void Promise.all([api.llmStatus().catch(() => null), api.getEmbeddingSettings().catch(() => null)]).then(
      ([llm, emb]) => {
        const mock: string[] = []
        if (llm?.tiers.some((t) => t.provider === 'mock')) mock.push('taalmodel')
        if (emb?.provider === 'mock') mock.push('embeddingmodel')
        setOfflineModels(mock)
      },
    )
  }, [step])

  const createWorkspace = async (workingDir: string) => {
    setBusy(true)
    setError(null)
    try {
      setCreated(await api.createWorkspace(name.trim(), workingDir.trim() || undefined))
      setStep('documents')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const upload = async (files: FileList | null) => {
    if (!created || !files?.length) return
    setBusy(true)
    for (const file of Array.from(files)) {
      const id = nextUploadId.current++
      const update = (patch: Partial<Upload>) =>
        setUploads((list) => list.map((u) => (u.id === id ? { ...u, ...patch } : u)))
      setUploads((list) => [...list, { id, name: file.name, state: 'bezig' }])
      try {
        const doc = await api.uploadDocument(file, created.id)
        const indexed = await api.indexDocument(doc.id)
        if (indexed.indexing_status === 'indexed') update({ state: 'klaar' })
        else update({ state: 'mislukt', detail: indexed.error_message ?? 'indexeren mislukt' })
      } catch (e) {
        update({ state: 'mislukt', detail: (e as Error).message })
      }
    }
    setBusy(false)
    if (fileInput.current) fileInput.current.value = ''
  }

  const finish = async (after: AfterSetup) => {
    if (!created) return
    setBusy(true)
    try {
      await onFinished(created, after)
    } catch (e) {
      setError(`De werkmap is aangemaakt, maar kon niet worden geladen: ${(e as Error).message}`)
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-xl">
        <div className="mb-5 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-slate-900 text-sm font-bold text-white">A</div>
          <span className="font-semibold text-slate-800">Welkom bij Apollo</span>
        </div>
        <Card>
          <Progress step={step} />

          {step === 'name' && (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (name.trim()) setStep('folder')
              }}
            >
              <h2 className="text-lg font-semibold">Geef je werkmap een naam</h2>
              <p className="mt-1 text-sm text-slate-500">
                Een werkmap bundelt de documenten van één onderwerp, met de analyses, vragen en bronnen die erbij horen.
                Zoeken en vragen stellen blijven binnen de werkmap.
              </p>
              <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="ws-name">
                Naam
              </label>
              <input
                id="ws-name"
                className={`${inputCls} mt-1`}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Bijvoorbeeld: Havenrenovatie"
                maxLength={256}
                autoFocus
              />
              <div className="mt-5 flex items-center gap-3">
                <Button onClick={() => name.trim() && setStep('folder')} disabled={!name.trim()}>
                  Volgende
                </Button>
                <button type="button" onClick={onSkip} className="text-xs text-slate-500 underline hover:text-slate-700">
                  Nu overslaan
                </button>
              </div>
            </form>
          )}

          {step === 'folder' && (
            <div>
              <h2 className="text-lg font-semibold">Waar komt “{name.trim()}” te staan?</h2>
              <p className="mt-1 text-sm text-slate-500">
                Elke werkmap is een map met een git-repository: je uploads worden daar bewaard en elke wijziging wordt
                vastgelegd. Kies een eigen map, of laat Apollo er zelf een aanmaken.
              </p>
              <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="ws-folder">
                Map <span className="font-normal text-slate-400">(volledig pad, optioneel)</span>
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  id="ws-folder"
                  className={`${inputCls} font-mono`}
                  value={folder}
                  onChange={(e) => setFolder(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && folder.trim()) void createWorkspace(folder)
                  }}
                  placeholder="C:/Documenten/Havenrenovatie"
                  spellCheck={false}
                  autoFocus
                />
                <Button variant="secondary" onClick={() => setPicking(true)} disabled={busy}>
                  Bladeren…
                </Button>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Een bestaande of nieuwe map. Draait Apollo in Docker, dan is dit een pad <em>in de container</em>; laat het
                dan leeg.
              </p>
              <ErrorText message={error} />
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button onClick={() => void createWorkspace(folder)} disabled={busy || !folder.trim()}>
                  {busy ? 'Aanmaken…' : 'Deze map gebruiken'}
                </Button>
                <Button variant="secondary" onClick={() => void createWorkspace('')} disabled={busy}>
                  Apollo kiest een map
                </Button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setError(null)
                    setStep('name')
                  }}
                  className="text-xs text-slate-500 underline hover:text-slate-700"
                >
                  Terug
                </button>
              </div>
            </div>
          )}

          {step === 'documents' && created && (
            <div>
              <h2 className="text-lg font-semibold">“{created.name}” staat klaar</h2>
              <p className="mt-1 break-all rounded bg-slate-100 px-2 py-1.5 font-mono text-xs text-slate-700">
                {created.working_dir}
              </p>

              <h3 className="mt-5 text-sm font-semibold text-slate-700">
                Voeg de eerste documenten toe <span className="font-normal text-slate-400">(optioneel)</span>
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                PDF, Word, Markdown of tekst. Ze worden in de werkmap bewaard en meteen doorzoekbaar gemaakt. Meer
                toevoegen kan later bij Documents, ook vanuit een GitHub-repository.
              </p>
              <input
                ref={fileInput}
                type="file"
                multiple
                accept=".pdf,.docx,.md,.txt"
                className="hidden"
                onChange={(e) => void upload(e.target.files)}
              />
              <div className="mt-3 flex flex-wrap items-start gap-2">
                <Button variant="secondary" onClick={() => fileInput.current?.click()} disabled={busy}>
                  Bestanden kiezen…
                </Button>
                <FolderUpload workspaceId={created.id} />
              </div>
              {uploads.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm">
                  {uploads.map((u) => (
                    <li key={u.id} className="flex items-baseline gap-2">
                      <span className={u.state === 'klaar' ? 'text-emerald-700' : u.state === 'mislukt' ? 'text-red-600' : 'text-slate-400'}>
                        {u.state === 'klaar' ? '✓' : u.state === 'mislukt' ? '✕' : '…'}
                      </span>
                      <span className="truncate">{u.name}</span>
                      {u.detail && <span className="truncate text-xs text-red-600">{u.detail}</span>}
                    </li>
                  ))}
                </ul>
              )}

              {offlineModels.length > 0 && (
                <p className="mt-5 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  Het {offlineModels.join(' en het ')} {offlineModels.length > 1 ? 'draaien' : 'draait'} nog offline (mock):
                  antwoorden zijn dan eenvoudige fragmenten en zoeken is niet echt semantisch. Stel een echt model in bij
                  Instellingen.
                </p>
              )}

              <ErrorText message={error} />
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button onClick={() => void finish('documents')} disabled={busy}>
                  {busy ? 'Even geduld…' : 'Afronden'}
                </Button>
                {offlineModels.length > 0 && (
                  <Button variant="secondary" onClick={() => void finish('settings')} disabled={busy}>
                    Afronden en modellen instellen
                  </Button>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
      {picking && (
        <FolderPickerModal
          initialPath={folder}
          title="Kies de map van de werkmap"
          onSelect={(path) => {
            setFolder(path)
            setPicking(false)
          }}
          onClose={() => setPicking(false)}
        />
      )}
    </div>
  )
}
