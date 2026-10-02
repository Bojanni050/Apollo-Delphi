import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import DocumentsPage from './pages/DocumentsPage'
import AnalysisPage from './pages/AnalysisPage'
import IssuesPage from './pages/IssuesPage'
import KnowledgePage from './pages/KnowledgePage'
import GeneratedPage from './pages/GeneratedPage'
import NotesPage from './pages/NotesPage'
import OraclesPage from './pages/OraclesPage'
import PulsePage from './pages/PulsePage'
import AskPage from './pages/AskPage'
import WeavePage from './pages/WeavePage'
import SearchPage from './pages/SearchPage'
import WorkspacePage from './pages/WorkspacePage'
import SettingsPage from './pages/SettingsPage'
import SetupWizard, { type AfterSetup } from './pages/SetupWizard'
import AppShell from './layout/AppShell'
import { LangContext, loadLang, saveLang, type Lang } from './i18n'
import DelphiChat from './DelphiChat'
import delphiIcon from './icons/delphi.png'
import { useTheme } from './theme'
import { GROUPS_CHANGED, usePulseRunning } from './pulseActivity'
import { api, type Workspace } from './api'

type Page = 'documents' | 'notes' | 'oracles' | 'search' | 'ask' | 'pulse' | 'weave' | 'analysis' | 'issues' | 'knowledge' | 'generated' | 'workspace' | 'settings'

/** A small network: three nodes and the lines between them (the icon of Delphi Weave). */
const WeaveIcon = (
  <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <path d="M5 14 10 5l5 9M5 14h10" strokeLinejoin="round" />
    <circle cx="5" cy="14" r="2" fill="currentColor" />
    <circle cx="10" cy="5" r="2" fill="currentColor" />
    <circle cx="15" cy="14" r="2" fill="currentColor" />
  </svg>
)

/** The working order first (Importeren, Delphi Pulse, Analyse, Delphi Weave), then a line, then the rest of the menu. */
const NAV: { id: Page; label: string; icon: ReactNode; dividerAfter?: boolean; sub?: { id: Page; label: string; icon: ReactNode }[] }[] = [
  {
    id: 'documents',
    label: 'Documenten',
    icon: '▦',
    sub: [
      { id: 'documents', label: 'Import', icon: '▦' },
      { id: 'notes', label: 'Notities', icon: '◑' },
      { id: 'oracles', label: 'Oracles', icon: '◎' },
    ],
  },
  { id: 'pulse', label: 'Delphi Pulse', icon: <img src={delphiIcon} alt="" className="h-5 w-5 object-contain" /> },
  { id: 'analysis', label: 'Analyse', icon: '◔' },
  { id: 'weave', label: 'Delphi Weave', icon: WeaveIcon, dividerAfter: true },
  { id: 'search', label: 'Zoeken', icon: '⌕' },
  { id: 'ask', label: 'Vragen', icon: '?' },
  { id: 'issues', label: 'Issues', icon: '⚠' },
  { id: 'knowledge', label: 'Knowledge', icon: '❖' },
  { id: 'generated', label: 'Generated', icon: '▤' },
  { id: 'workspace', label: 'Werkmap', icon: '⎇' },
  { id: 'settings', label: 'Instellingen', icon: '⚙' },
]

const CONTEXT_TITLES: Record<Page, string> = {
  documents: 'Document details',
  notes: 'Notitie',
  oracles: 'Oracle',
  search: 'Fragment',
  ask: 'Bronnen',
  pulse: 'Voorstel',
  weave: 'Verbinding',
  workspace: 'Repository',
  settings: 'Model',
  analysis: 'Run details',
  issues: 'Issue context',
  knowledge: 'Provenance',
  generated: 'Verification',
}

export default function App() {
  useTheme() // applies the chosen theme (also on the setup wizard, which has no top bar)
  const [lang, setLang] = useState<Lang>(loadLang) // Dutch by default; remembered in this browser or app window
  const chooseLang = (l: Lang) => {
    setLang(l)
    saveLang(l)
    window.location.reload() // the interface texts are read once; a reload applies the choice everywhere
  }
  const [page, setPage] = useState<Page>('documents')
  const pulseRunning = usePulseRunning()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  // true once the list has been fetched: an empty list before that must not show the setup wizard
  const [workspacesLoaded, setWorkspacesLoaded] = useState(false)
  const [wizardSkipped, setWizardSkipped] = useState(false)
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDir, setNewDir] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // What the working order in the top bar depends on: are there documents, and are there groups (Analyse needs them)
  const [hasDocuments, setHasDocuments] = useState(false)
  const [hasGroups, setHasGroups] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const loadWorkspaces = async (preserveActive = true) => {
    try {
      const list = await api.listWorkspaces()
      setWorkspaces(list)
      setWorkspacesLoaded(true)
      if (!preserveActive || activeWorkspaceId === null || !list.some((w) => w.id === activeWorkspaceId)) {
        const stored = localStorage.getItem('apollo.activeWorkspaceId')
        const id = stored ? Number(stored) : null
        setActiveWorkspaceId(list.some((w) => w.id === id) ? id : (list[0]?.id ?? null))
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    void loadWorkspaces()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (activeWorkspaceId !== null) localStorage.setItem('apollo.activeWorkspaceId', String(activeWorkspaceId))
  }, [activeWorkspaceId])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const createWorkspace = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      const ws = await api.createWorkspace(name, newDir.trim() || undefined)
      setNewName('')
      setNewDir('')
      setCreating(false)
      setMenuOpen(false)
      await loadWorkspaces(false)
      setActiveWorkspaceId(ws.id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const finishSetup = async (ws: Workspace, after: AfterSetup) => {
    await loadWorkspaces(false)
    setActiveWorkspaceId(ws.id)
    setPage(after)
  }

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? null

  const refreshFlow = useCallback(async () => {
    if (activeWorkspaceId === null) {
      setHasDocuments(false)
      setHasGroups(false)
      return
    }
    try {
      const docs = await api.listDocuments(activeWorkspaceId)
      setHasDocuments(docs.length > 0)
      setHasGroups(docs.some((d) => !!d.group_name))
    } catch {
      /* the next look tries again */
    }
  }, [activeWorkspaceId])
  // look again when the werkmap or the page changes, and when Delphi Pulse has accepted something (that is what creates groups)
  useEffect(() => {
    void refreshFlow()
  }, [refreshFlow, page])
  useEffect(() => {
    window.addEventListener(GROUPS_CHANGED, refreshFlow)
    return () => window.removeEventListener(GROUPS_CHANGED, refreshFlow)
  }, [refreshFlow])
  const activeLabel = NAV.find((n) => n.id === page)?.label ?? page

  const workspaceBar = (
    <div className="relative">
      <div className="flex items-center gap-1">
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-slate-200 px-2 py-1.5 text-left text-sm hover:bg-slate-50"
          title="Werkmap wisselen"
        >
          <span className="text-slate-400">📁</span>
          <span className="truncate font-medium text-slate-800">
            {activeWorkspace ? activeWorkspace.name : 'Geen werkmap'}
          </span>
          <span className="ml-auto text-slate-400">▾</span>
        </button>
      </div>
      {menuOpen && (
        <div ref={menuRef} className="absolute left-0 right-0 top-full z-20 mt-1 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          {workspaces.map((w) => (
            <button
              key={w.id}
              onClick={() => {
                setActiveWorkspaceId(w.id)
                setMenuOpen(false)
              }}
              className={`flex w-full items-center rounded-lg px-2 py-1.5 text-left text-sm ${
                w.id === activeWorkspaceId ? 'bg-slate-100 font-medium' : 'hover:bg-slate-50'
              }`}
            >
              <span className="truncate">{w.name}</span>
            </button>
          ))}
          {workspaces.length === 0 && (
            <p className="px-2 py-1.5 text-xs text-slate-400">Nog geen werkmaps.</p>
          )}
          <div className="mt-1 border-t border-slate-100 pt-1">
            {creating ? (
              <div className="px-1 py-1">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void createWorkspace()
                    if (e.key === 'Escape') setCreating(false)
                  }}
                  placeholder="Naam nieuwe werkmap…"
                  className="w-full rounded-lg border border-slate-300 px-2 py-1 text-sm"
                />
                <input
                  value={newDir}
                  onChange={(e) => setNewDir(e.target.value)}
                  placeholder="Map (optioneel, absoluut pad)"
                  className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1 text-xs"
                />
                <button
                  onClick={() => void createWorkspace()}
                  className="mt-1 w-full rounded-lg bg-slate-900 px-2 py-1 text-xs font-medium text-white hover:bg-slate-700"
                >
                  Aanmaken
                </button>
              </div>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50"
              >
                <span className="text-slate-400">＋</span> Nieuwe werkmap…
              </button>
            )}
          </div>
        </div>
      )}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )

  if (workspacesLoaded && workspaces.length === 0 && !wizardSkipped) {
    return (
      <LangContext.Provider value={lang}>
        <SetupWizard onFinished={finishSetup} onSkip={() => setWizardSkipped(true)} />
      </LangContext.Provider>
    )
  }

  return (
    <LangContext.Provider value={lang}>
    <AppShell
      flow={[
        { id: 'documents', label: 'Import', done: hasDocuments },
        { id: 'pulse', label: 'Delphi Pulse', done: hasGroups },
        {
          id: 'analysis',
          label: 'Analyse',
          disabled: !hasGroups,
          title: hasGroups ? 'Analyseer de hele werkmap of een of meer groepen' : 'Maak eerst groepen: draai Delphi Pulse en accepteer de voorstellen',
        },
      ]}
      nav={NAV.map((n) =>
        n.id === 'pulse'
          ? { ...n, busy: pulseRunning }
          : n.id === 'analysis'
            ? { ...n, disabled: !hasGroups, title: 'Maak eerst groepen: draai Delphi Pulse en accepteer de voorstellen' }
            : n,
      )}
      active={page}
      onNavigate={(id) => setPage(id as Page)}
      breadcrumb={
        <span className="truncate text-sm font-medium text-slate-700">
          {activeWorkspace ? `${activeWorkspace.name} / ` : ''}
          {activeLabel}
        </span>
      }
      contextTitle={CONTEXT_TITLES[page]}
      workspaceBar={workspaceBar}
    >
      {page === 'issues' && <IssuesPage workspaceId={activeWorkspaceId} />}
      {page === 'generated' && <GeneratedPage workspaceId={activeWorkspaceId} />}
      {page === 'notes' && <NotesPage workspaceId={activeWorkspaceId} />}
      {page === 'oracles' && <OraclesPage workspaceId={activeWorkspaceId} />}
      {(page === 'documents' || page === 'search' || page === 'ask' || page === 'pulse' || page === 'weave' || page === 'analysis' || page === 'knowledge' || page === 'workspace' || page === 'settings') && (
        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-6">
          <div className="mx-auto max-w-5xl">
            {page === 'documents' && <DocumentsPage workspaceId={activeWorkspaceId} workspaceName={activeWorkspace?.name} onChanged={() => void loadWorkspaces()} />}
            {page === 'search' && <SearchPage workspaceId={activeWorkspaceId} workspaceName={activeWorkspace?.name} />}
            {page === 'ask' && <AskPage workspaceId={activeWorkspaceId} />}
            {page === 'pulse' && <PulsePage workspaceId={activeWorkspaceId} />}
            {page === 'weave' && <WeavePage workspaceId={activeWorkspaceId} />}
            {page === 'workspace' && <WorkspacePage workspace={activeWorkspace} />}
            {page === 'settings' && <SettingsPage onChooseLang={chooseLang} />}
            {page === 'analysis' && <AnalysisPage workspaceId={activeWorkspaceId} />}
            {page === 'knowledge' && <KnowledgePage workspaceId={activeWorkspaceId} />}
          </div>
        </div>
      )}
      {/* Delphi floats above every screen: her orb opens her chat, and dragging moves her out of the way */}
      <DelphiChat workspaceId={activeWorkspaceId} />
    </AppShell>
    </LangContext.Provider>
  )
}
