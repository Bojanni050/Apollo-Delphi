import { useEffect, useState } from 'react'
import { api, type Commit, type Workspace } from '../api'
import { Card, ErrorText } from '../components'

export default function WorkspacePage({ workspace }: { workspace: Workspace | null }) {
  const [commits, setCommits] = useState<Commit[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setCommits([])
    setError(null)
    if (!workspace) return
    api
      .workspaceHistory(workspace.id)
      .then(setCommits)
      .catch((e: Error) => setError(e.message))
  }, [workspace])

  if (!workspace) return <Card>Kies of maak eerst een werkmap.</Card>

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold">{workspace.name}</h2>
        <p className="mt-1 text-sm text-slate-500">Deze werkmap is een git-repository op schijf.</p>
        <p className="mt-3 break-all rounded-lg bg-slate-100 px-2 py-1.5 font-mono text-xs text-slate-700">
          {workspace.working_dir ?? 'Nog geen map — wordt aangemaakt bij de eerste upload.'}
        </p>
        <ErrorText message={error} />
      </Card>

      <Card>
        <h3 className="mb-3 font-semibold">Geschiedenis</h3>
        {commits.length === 0 ? (
          <p className="text-sm text-slate-500">Nog geen commits.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {commits.map((c) => (
              <li key={c.sha} className="flex items-baseline gap-3 py-1.5">
                <code className="text-xs text-slate-400">{c.sha.slice(0, 7)}</code>
                <span className="min-w-0 flex-1 truncate">{c.message}</span>
                <time className="shrink-0 text-xs text-slate-400">{new Date(c.date).toLocaleString('nl-NL')}</time>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
