import { useState } from 'react'
import DocumentsPage from './pages/DocumentsPage'
import AnalysisPage from './pages/AnalysisPage'
import IssuesPage from './pages/IssuesPage'
import KnowledgePage from './pages/KnowledgePage'
import GeneratedPage from './pages/GeneratedPage'
import AppShell from './layout/AppShell'

type Page = 'documents' | 'analysis' | 'issues' | 'knowledge' | 'generated'

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: 'documents', label: 'Documents', icon: '▦' },
  { id: 'analysis', label: 'Analysis', icon: '◔' },
  { id: 'issues', label: 'Issues', icon: '⚠' },
  { id: 'knowledge', label: 'Knowledge', icon: '❖' },
  { id: 'generated', label: 'Generated', icon: '▤' },
]

const CONTEXT_TITLES: Record<Page, string> = {
  documents: 'Document details',
  analysis: 'Run details',
  issues: 'Issue context',
  knowledge: 'Provenance',
  generated: 'Verification',
}

export default function App() {
  const [page, setPage] = useState<Page>('issues')
  const activeLabel = NAV.find((n) => n.id === page)?.label ?? page

  return (
    <AppShell
      nav={NAV}
      active={page}
      onNavigate={(id) => setPage(id as Page)}
      breadcrumb={<span className="truncate text-sm font-medium text-slate-700">{activeLabel}</span>}
      contextTitle={CONTEXT_TITLES[page]}
    >
      {page === 'issues' && <IssuesPage />}
      {page === 'generated' && <GeneratedPage />}
      {(page === 'documents' || page === 'analysis' || page === 'knowledge') && (
        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-6">
          <div className="mx-auto max-w-5xl">
            {page === 'documents' && <DocumentsPage />}
            {page === 'analysis' && <AnalysisPage />}
            {page === 'knowledge' && <KnowledgePage />}
          </div>
        </div>
      )}
    </AppShell>
  )
}
