import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { api, serverDate, type DocumentRecord } from '../api'
import { Button, Card, ErrorText, StatusBadge } from '../components'
import FolderUpload from './FolderUpload'
import IndexProgress from './IndexProgress'
import { useReader } from '../reader'
import UnassignedBanner from './UnassignedBanner'

/** The value of the group filter (and the key of the heading) for documents that have no group. */
const NO_GROUP = '__none__'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function DocumentsPage({
  workspaceId,
  workspaceName,
  onChanged,
}: {
  workspaceId?: number | null
  workspaceName?: string | null
  onChanged?: () => void
}) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const reader = useReader()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // the virtual folders (groups): '' = all, NO_GROUP = the documents without one
  const [groupFilter, setGroupFilter] = useState('')
  const groupCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const d of documents) counts.set(d.group_name ?? NO_GROUP, (counts.get(d.group_name ?? NO_GROUP) ?? 0) + 1)
    return counts
  }, [documents])
  const groupNames = useMemo(() => [...groupCounts.keys()].filter((g) => g !== NO_GROUP).sort((a, b) => a.localeCompare(b, 'nl')), [groupCounts])
  // without any group the list stays flat; with groups it gets a heading per group (documents without one last)
  const sections = useMemo(() => {
    const shown = groupFilter ? documents.filter((d) => (d.group_name ?? NO_GROUP) === groupFilter) : documents
    if (groupNames.length === 0) return [{ group: null as string | null, docs: shown }]
    return [...groupNames, NO_GROUP]
      .map((g) => ({ group: g as string | null, docs: shown.filter((d) => (d.group_name ?? NO_GROUP) === g) }))
      .filter((section) => section.docs.length > 0)
  }, [documents, groupFilter, groupNames])
  useEffect(() => {
    if (groupFilter && !groupCounts.has(groupFilter)) setGroupFilter('') // that group is gone (documents deleted or moved)
  }, [groupFilter, groupCounts])
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
      <UnassignedBanner
        workspaceId={workspaceId}
        workspaceName={workspaceName}
        onAdopted={() => {
          void refresh()
          onChanged?.()
        }}
      />
      <IndexProgress
        workspaceId={workspaceId ?? null}
        waiting={documents.filter((d) => d.indexing_status === 'pending' || d.indexing_status === 'failed' || d.indexing_status === 'parsed').length}
        onProgress={() => void refresh()}
      />
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
        <div className="mt-4 border-t border-slate-100 pt-4">
          <p className="text-sm text-slate-500 mb-2">
            Of een hele map: alle submappen worden doorlopen en elk ondersteund bestand komt erin met zijn pad.
          </p>
          <FolderUpload workspaceId={workspaceId ?? null} onChanged={() => { onChanged?.(); void refresh() }} />
        </div>
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
            className="flex-1 border rounded-lg px-3 py-1.5 text-sm"
            disabled={repoBusy}
          />
          <Button onClick={() => void ingestRepo()} disabled={repoBusy || !repoUrl.trim()}>
            {repoBusy ? 'Ophalen…' : 'Repository toevoegen'}
          </Button>
        </div>
        {repoMessage && <p className="text-sm mt-2 text-slate-600">{repoMessage}</p>}
      </Card>

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Documents</h2>
          {groupNames.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Groep
              <select
                value={groupFilter}
                onChange={(e) => setGroupFilter(e.target.value)}
                className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="">Alle groepen ({documents.length})</option>
                {groupNames.map((g) => (
                  <option key={g} value={g}>
                    {g} ({groupCounts.get(g)})
                  </option>
                ))}
                {groupCounts.has(NO_GROUP) && <option value={NO_GROUP}>Zonder groep ({groupCounts.get(NO_GROUP)})</option>}
              </select>
            </label>
          )}
        </div>
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
            {sections.map(({ group, docs }) => (
              <Fragment key={group ?? 'flat'}>
                {group !== null && (
                  <tr>
                    <td colSpan={6} className="pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {group === NO_GROUP ? 'Zonder groep' : group} · {docs.length}
                    </td>
                  </tr>
                )}
                {docs.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => reader.open({ documentId: d.id })}
                    title="Klik om dit document te lezen"
                    className={`cursor-pointer border-b last:border-0 hover:bg-slate-50 ${
                      reader.isOpen && reader.target?.documentId === d.id ? 'bg-slate-100' : ''
                    }`}
                  >
                    <td className="py-2 font-medium">{d.source_type === 'github' && <span className="mr-1 text-slate-400" title={d.source_url ?? ''}>⌥</span>}
                      {d.filename}
                      {d.inbox_path && !d.inbox_path.startsWith('Inbox/') && (
                        <p className="mt-0.5 text-xs font-normal text-slate-400" title="Waar het bestand in de git-werkmap staat">
                          {d.inbox_path.split('/')[0]}/
                        </p>
                      )}
                      {d.error_message && (
                        <p className="text-xs text-red-600 mt-1" title={d.error_message}>
                          {d.error_message.slice(0, 120)}
                        </p>
                      )}
                    </td>
                    <td className="uppercase">{d.file_type}</td>
                    <td>{formatSize(d.file_size)}</td>
                    <td><StatusBadge status={d.indexing_status} /></td>
                    <td className="text-slate-500">{serverDate(d.created_at).toLocaleString()}</td>
                    <td className="text-right space-x-2 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <Button variant="secondary" onClick={() => void indexDoc(d.id)} disabled={busy}>
                        Index
                      </Button>
                      <Button variant="danger" onClick={() => void deleteDoc(d.id)} disabled={busy}>
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </Fragment>
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
    </div>
  )
}
