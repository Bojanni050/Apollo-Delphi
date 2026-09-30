import { useState, type ReactNode } from 'react'
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

const PAGE_META: Record<Page, { crumb: string; contextTitle: string; context: ReactNode }> = {
  documents: {
    crumb: 'Documents',
    contextTitle: 'Document details',
    context: <ContextBlock lines={['Select a document to preview metadata, chunks and indexing status here.']} />,
  },
  analysis: {
    crumb: 'Analysis',
    contextTitle: 'Run details',
    context: (
      <ContextBlock
        lines={[
          'Shows the active analysis run: stats, timing and step breakdown.',
          'Collapsed by default — open it when you need run-level context.',
        ]}
      />
    ),
  },
  issues: {
    crumb: 'Issues',
    contextTitle: 'Issue context',
    context: (
      <ContextBlock
        lines={[
          'Contextual panel for the selected issue.',
          'Resolution proposal, confidence and decision history appear here.',
        ]}
      />
    ),
  },
  knowledge: {
    crumb: 'Knowledge',
    contextTitle: 'Provenance',
    context: <ContextBlock lines={['Provenance and confidence for the selected knowledge item.']} />,
  },
  generated: {
    crumb: 'Generated',
    contextTitle: 'Verification',
    context: <ContextBlock lines={['Verification findings for the selected generated document.']} />,
  },
}

export default function App() {
  const [page, setPage] = useState<Page>('issues')
  const meta = PAGE_META[page]
  const activeLabel = NAV.find((n) => n.id === page)?.label ?? page

  return (
    <AppShell
      nav={NAV}
      active={page}
      onNavigate={(id) => setPage(id as Page)}
      breadcrumb={
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="hover:text-slate-800">Workspace</span>
          <span className="text-slate-300">/</span>
          <span className="hover:text-slate-800">{activeLabel}</span>
          <span className="text-slate-300">/</span>
          <span className="truncate font-mono text-xs text-slate-400">{meta.crumb} · latest</span>
        </span>
      }
      topActions={
        <>
          <button className="rounded border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">
            View API ▾
          </button>
          <button className="rounded bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-500">
            Primary action
          </button>
        </>
      }
      contextTitle={meta.contextTitle}
      contextPane={meta.context}
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

function ContextBlock({ lines }: { lines: string[] }) {
  return (
    <div className="space-y-3 text-sm text-slate-600">
      {lines.map((l, i) => (
        <p key={i}>{l}</p>
      ))}
      <div className="rounded border border-dashed border-slate-300 p-3 text-xs text-slate-400">
        Contextual panel — collapsed by default. Content changes per page / selection.
      </div>
    </div>
  )
}
