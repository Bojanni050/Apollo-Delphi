import { useEffect, useState } from 'react'
import { api, type GeneratedDocument } from '../api'
import { Card, ErrorText, StatusBadge } from '../components'
import { SplitView } from '../layout/AppShell'

function renderMarkdown(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-4">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-semibold mt-2">$1</h1>')
    .replace(/^- (.+)$/gm, '<li class="ml-5 list-disc">$1</li>')
    .replace(/\n{2,}/g, '<br/><br/>')
}

/** The oracles made of Delphi's answers: generated documents of kind "oracle", one per exchange. */
export default function OraclesPage({ workspaceId }: { workspaceId?: number | null }) {
  const [oracles, setOracles] = useState<GeneratedDocument[]>([])
  const [selected, setSelected] = useState<GeneratedDocument | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSelected(null)
    setError(null)
    api
      .listGenerated(workspaceId, 'oracle')
      .then(setOracles)
      .catch(() => setError('Could not load the oracles'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId])

  return (
    <SplitView
      initialWidth={320}
      listPane={
        <div className="p-3">
          <h2 className="font-semibold mb-3 px-1">Oracles</h2>
          <ul className="space-y-1 text-sm">
            {oracles.map((d) => (
              <li key={d.id}>
                <button
                  onClick={() => setSelected(d)}
                  className={`w-full text-left p-2 rounded-lg border ${
                    selected?.id === d.id ? 'border-slate-900 bg-slate-50' : 'hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between items-center gap-2">
                    <span className="font-medium line-clamp-1">{d.title}</span>
                    <StatusBadge status={d.status} />
                  </div>
                  <span className="text-xs text-slate-400">{new Date(d.created_at).toLocaleString()}</span>
                </button>
              </li>
            ))}
            {oracles.length === 0 && (
              <li className="text-slate-400 px-1">
                Nog geen oracles. Vraag Delphi iets en maak van haar antwoord een oracle.
              </li>
            )}
          </ul>
          <ErrorText message={error} />
        </div>
      }
      detailPane={
        selected ? (
          <Card>
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">{selected.title}</h2>
              <StatusBadge status={selected.status} />
            </div>
            <div
              className="prose prose-sm mt-3 text-sm"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(selected.content ?? '') }}
            />
          </Card>
        ) : (
          <Card>
            <p className="text-slate-400 text-sm">
              Oracles ontstaan uit Delphi's antwoorden: vraag haar iets in de chat en maak van het antwoord een
              oracle. Ze verschijnen hier en in de werkmap onder Oracles/.
            </p>
          </Card>
        )
      }
    />
  )
}
