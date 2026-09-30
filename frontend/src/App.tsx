import { useState } from 'react'
import DocumentsPage from './pages/DocumentsPage'
import AnalysisPage from './pages/AnalysisPage'
import IssuesPage from './pages/IssuesPage'
import KnowledgePage from './pages/KnowledgePage'
import GeneratedPage from './pages/GeneratedPage'

type Page = 'documents' | 'analysis' | 'issues' | 'knowledge' | 'generated'

const NAV: { id: Page; label: string }[] = [
  { id: 'documents', label: 'Documents' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'issues', label: 'Issues' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'generated', label: 'Generated Documents' },
]

export default function App() {
  const [page, setPage] = useState<Page>('documents')

  return (
    <div className="min-h-screen">
      <header className="bg-slate-900 text-white">
        <div className="mx-auto max-w-6xl px-6 py-4 flex items-center gap-8">
          <h1 className="text-xl font-semibold tracking-wide">Apollo</h1>
          <nav className="flex gap-1">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => setPage(n.id)}
                className={`px-3 py-1.5 rounded text-sm ${
                  page === n.id ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        {page === 'documents' && <DocumentsPage />}
        {page === 'analysis' && <AnalysisPage />}
        {page === 'issues' && <IssuesPage />}
        {page === 'knowledge' && <KnowledgePage />}
        {page === 'generated' && <GeneratedPage />}
      </main>
    </div>
  )
}
