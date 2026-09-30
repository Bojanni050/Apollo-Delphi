import { useEffect, useRef, useState } from 'react'
import { api, type DocumentRecord, type SearchHit } from '../api'
import { Button, Card, ErrorText, StatusBadge } from '../components'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function DocumentsPage({ workspaceId, onChanged }: { workspaceId?: number | null; onChanged?: () => void }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchHit[] | null>(null)
  const [repoUrl, setRepoUrl] = useState('')
  const [repoBusy, setRepoBusy] = useState(false)
  const [repoMessage, setRepoMessage] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = async () => {
    try {
      setDocuments(await api.listDocuments(workspaceId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    void refresh()
  }, [workspaceId])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    setError(null)
    try {
      for (const file of Array.from(files)) {
        await api.uploadDocument(file, workspaceId)
        onChanged?.()
      }
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const indexDoc = async (id: number) => {
    setBusy(true)
    setError(null)
    try {
      await api.indexDocument(id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const deleteDoc = async (id: number) => {
    setBusy(true)
    try {
      await api.deleteDocument(id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const runSearch = async () => {
    if (!searchQuery.trim()) return
    setError(null)
    try {
      const res = await api.search(searchQuery)
      setSearchResults(res.results)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const ingestRepo = async () => {
    const url = repoUrl.trim()
    if (!url) return
    setRepoBusy(true)
    setRepoMessage(null)
    try {
      const result = await api.ingestGithub(url, workspaceId)
      setRepoMessage(
        `${result.repository}: ${result.documents_created} document aangemaakt van ${result.files_selected} bestanden` +
          (result.errors.length ? ` (${result.errors.length} fouten)` : ''),
      )
      setRepoUrl('')
      await refresh()
      onChanged?.()
    } catch (e) {
      setRepoMessage(`Fout: ${(e as Error).message}`)
    } finally {
      setRepoBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <h2 className="text-lg font-semibold mb-3">Upload documents</h2>
        <p className="text-sm text-slate-500 mb-3">Supported: PDF, DOCX, TXT, Markdown. Files are validated and indexed server-side.</p>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => void upload(e.target.files)}
          disabled={busy}
          className="text-sm"
        />
        <ErrorText message={error} />
      </Card>

      <Card>
        <h2 className="text-lg font-semibold mb-3">GitHub repository</h2>
        <p className="text-sm text-slate-500 mb-3">
          Voeg een publieke GitHub-repository toe. De inhoud (docs, config, code) wordt gedownload en als
          één document geïndexeerd, zodat analyse discrepanties tussen je documenten en de repo vindt.
        </p>
        <div className="flex gap-2">
          <input
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void ingestRepo()}
            placeholder="https://github.com/owner/repo"
            className="flex-1 border rounded px-3 py-1.5 text-sm"
            disabled={repoBusy}
          />
          <Button onClick={() => void ingestRepo()} disabled={repoBusy || !repoUrl.trim()}>
            {repoBusy ? 'Ophalen…' : 'Repository toevoegen'}
          </Button>
        </div>
        {repoMessage && <p className="text-sm mt-2 text-slate-600">{repoMessage}</p>}
      </Card>

      <Card>
        <h2 className="text-lg font-semibold mb-3">Documents</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b">
              <th className="py-2">Name</th>
              <th>Type</th>
              <th>Size</th>
              <th>Status</th>
              <th>Uploaded</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {documents.map((d) => (
              <tr key={d.id} className="border-b last:border-0">
                <td className="py-2 font-medium">{d.source_type === 'github' && <span className="mr-1 text-slate-400" title={d.source_url ?? ''}>⌥</span>}
                  {d.filename}
                  {d.error_message && (
                    <p className="text-xs text-red-600 mt-1" title={d.error_message}>
                      {d.error_message.slice(0, 120)}
                    </p>
                  )}
                </td>
                <td className="uppercase">{d.file_type}</td>
                <td>{formatSize(d.file_size)}</td>
                <td><StatusBadge status={d.indexing_status} /></td>
                <td className="text-slate-500">{new Date(d.created_at).toLocaleString()}</td>
                <td className="text-right space-x-2 whitespace-nowrap">
                  <Button variant="secondary" onClick={() => void indexDoc(d.id)} disabled={busy}>
                    Index
                  </Button>
                  <Button variant="danger" onClick={() => void deleteDoc(d.id)} disabled={busy}>
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
            {documents.length === 0 && (
              <tr>
                <td colSpan={6} className="py-6 text-center text-slate-400">
                  No documents uploaded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold mb-3">Semantic search</h2>
        <div className="flex gap-2">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void runSearch()}
            placeholder="Search indexed documents…"
            className="flex-1 border rounded px-3 py-1.5 text-sm"
          />
          <Button onClick={() => void runSearch()}>Search</Button>
        </div>
        {searchResults && (
          <ul className="mt-4 space-y-3">
            {searchResults.map((r) => (
              <li key={r.chunk_id} className="border rounded p-3 text-sm">
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span className="font-medium text-slate-700">{r.document_filename}</span>
                  <span>
                    {r.page_number ? `page ${r.page_number}` : ''} · similarity {r.similarity.toFixed(3)}
                  </span>
                </div>
                <p className="line-clamp-3 text-slate-600">{r.excerpt}</p>
              </li>
            ))}
            {searchResults.length === 0 && <li className="text-slate-400 text-sm">No results.</li>}
          </ul>
        )}
      </Card>
    </div>
  )
}
