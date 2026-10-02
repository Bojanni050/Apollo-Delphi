import { useEffect, useState } from 'react'
import { api, formatLines, type Issue, type IssueDetail } from '../api'
import { Button, Card, ErrorText, StatusBadge } from '../components'
import { SplitView } from '../layout/AppShell'
import { useReader } from '../reader'
import { useT } from '../i18n'

const NO_GROUP = '__none__'

export default function IssuesPage({ workspaceId }: { workspaceId?: number | null }) {
  const t = useT()
  const reader = useReader()
  const [issues, setIssues] = useState<Issue[]>([])
  const [selected, setSelected] = useState<IssueDetail | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // show only the issues of one group (virtual folder): '' = every group, NO_GROUP = documents without one
  const [group, setGroup] = useState('')
  const [groups, setGroups] = useState<{ names: string[]; hasUngrouped: boolean }>({ names: [], hasUngrouped: false })
  const loadIssues = async (g: string | null = null) => {
    const all = await api.listIssues(undefined, workspaceId, g)
    setIssues(all)
    return all
  }

  useEffect(() => {
    setSelected(null)
    setError(null)
    setGroup('')
    setGroups({ names: [], hasUngrouped: false })
    void loadIssues(null).catch((e) => setError((e as Error).message))
    if (workspaceId === null) return
    let cancelled = false
    api
      .listDocuments(workspaceId)
      .then((docs) => {
        if (cancelled) return
        const names = [...new Set(docs.map((d) => d.group_name).filter((g): g is string => !!g))].sort()
        setGroups({ names, hasUngrouped: docs.some((d) => !d.group_name) })
      })
      .catch(() => {
        /* the filter simply stays empty */
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId])

  useEffect(() => {
    // refetch when the chosen group changes (skipped on the first render: that load belongs to the effect above)
    if (group === '' && groups.names.length === 0 && !groups.hasUngrouped) return
    setSelected(null)
    void loadIssues(group || null).catch((e) => setError((e as Error).message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group])

  const select = async (id: number) => {
    setError(null)
    try {
      setSelected(await api.getIssue(id))
      setNote('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const investigate = async (id: number) => {
    setBusy(true)
    setError(null)
    try {
      setSelected(await api.investigateIssue(id))
      await loadIssues(group || null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const decide = async (id: number, decision: 'accept' | 'reject' | 'unresolved') => {
    setBusy(true)
    setError(null)
    try {
      await api.resolveIssue(id, decision, note || undefined)
      setSelected(await api.getIssue(id))
      await loadIssues(group || null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SplitView
      initialWidth={320}
      listPane={
        <div className="p-3">
          <h2 className="font-semibold mb-3 px-1">{t('issues.title')}</h2>
          {(groups.names.length > 0 || groups.hasUngrouped) && (
            <select
              value={group}
              onChange={(e) => setGroup(e.target.value)}
              aria-label={t('issues.filterGroup')}
              title={t('issues.filterGroupHint')}
              className="mb-3 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
            >
              <option value="">{t('issues.allGroups')}</option>
              {groups.names.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
              {groups.hasUngrouped && <option value={NO_GROUP}>{t('issues.noGroup')}</option>}
            </select>
          )}
          <ul className="space-y-2 text-sm">
            {issues.map((i) => (
              <li key={i.id}>
                <button
                  onClick={() => void select(i.id)}
                  className={`w-full text-left p-2 rounded-lg border ${
                    selected?.id === i.id ? 'border-slate-900 bg-slate-50' : 'hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between items-center gap-2">
                    <span className="font-medium line-clamp-2">{i.title}</span>
                    <StatusBadge status={i.status} />
                  </div>
                  <span className="text-xs text-slate-400">{i.issue_type}</span>
                </button>
              </li>
            ))}
            {issues.length === 0 && <li className="text-slate-400">{t('issues.empty')}</li>}
          </ul>
        </div>
      }
      detailPane={
        <div className="space-y-4">
          {!selected && <Card><p className="text-slate-400 text-sm">{t('issues.select')}</p></Card>}
          {selected && (
            <>
              <Card>
                <div className="flex justify-between items-start">
                  <div>
                    <h2 className="text-lg font-semibold">{selected.title}</h2>
                    <p className="text-sm text-slate-500 mt-1">{selected.description}</p>
                  </div>
                  <StatusBadge status={selected.status} />
                </div>
                <div className="mt-3 flex gap-2">
                  <Button onClick={() => void investigate(selected.id)} disabled={busy}>
                    {busy ? t('issues.investigating') : t('issues.investigate')}
                  </Button>
                </div>
                <ErrorText message={error} />
              </Card>

              <Card>
                <h3 className="font-semibold mb-2">{t('issues.conflictingClaims')}</h3>
                <ul className="space-y-2 text-sm">
                  {selected.claims.map((c) => (
                    <li key={c.id} className="border-b last:border-0 pb-2">
                      <p>{c.statement}</p>
                      <span className="text-xs text-slate-400">
                        {t('issues.document')} #{c.document_id} · {t('issues.value')} {c.value ?? '—'} {c.unit ?? ''} · <StatusBadge status={c.status} />
                      </span>
                    </li>
                  ))}
                  {selected.claims.length === 0 && <li className="text-slate-400">{t('issues.noClaims')}</li>}
                </ul>
              </Card>

              <Card>
                <h3 className="font-semibold mb-2">{t('issues.evidence')}</h3>
                <ul className="space-y-2 text-sm">
                  {selected.evidence.map((e) => (
                    <li key={e.id} className="border rounded-lg p-2">
                      <div className="text-xs text-slate-400 mb-1">
                        document #{e.document_id} {e.page_number ? `· ${t('issues.page')} ${e.page_number}` : ''} {e.section ? `· ${e.section}` : ''} {e.line_start != null ? `· ${formatLines(e.line_start, e.line_end)}` : ''} · {e.evidence_type}
                      </div>
                      <p className="text-slate-600">{e.original_text}</p>
                      <button
                        onClick={() =>
                          reader.open({ documentId: e.document_id, lineStart: e.line_start, lineEnd: e.line_end, excerpt: e.original_text, page: e.page_number })
                        }
                        className="mt-1 text-xs text-slate-500 underline hover:text-slate-800"
                      >
                        Lees in het leesvenster
                      </button>
                    </li>
                  ))}
                  {selected.evidence.length === 0 && <li className="text-slate-400">{t('issues.noEvidence')}</li>}
                </ul>
              </Card>

              {selected.resolution && (
                <Card>
                  <h3 className="font-semibold mb-2">{t('issues.resolution')}</h3>
                  <p className="text-sm">
                    <span className="font-medium">{t('issues.conclusion')}: </span>
                    {selected.resolution.conclusion ?? '—'}
                  </p>
                  <p className="text-sm mt-1">
                    <span className="font-medium">{t('issues.reasoning')}: </span>
                    {selected.resolution.reasoning ?? '—'}
                  </p>
                  <p className="text-sm mt-1">
                    <span className="font-medium">{t('issues.status')}: </span>
                    <StatusBadge status={selected.resolution.status} />
                    <span className="ml-2 text-slate-400">
                      {t('issues.confidence')} {selected.resolution.confidence.toFixed(2)} · {selected.resolution.explanation_type ?? '—'}
                    </span>
                  </p>
                  {selected.resolution.unresolved_uncertainty && (
                    <p className="text-sm mt-1 text-amber-700">
                      <span className="font-medium">{t('issues.unresolvedUncertainty')}: </span>
                      {selected.resolution.unresolved_uncertainty}
                    </p>
                  )}
                  <div className="mt-3 space-y-2">
                    <textarea
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder={t('issues.note')}
                      className="w-full border rounded-lg px-2 py-1.5 text-sm"
                      rows={2}
                    />
                    <div className="flex gap-2">
                      <Button onClick={() => void decide(selected.id, 'accept')} disabled={busy}>{t('issues.accept')}</Button>
                      <Button variant="secondary" onClick={() => void decide(selected.id, 'reject')} disabled={busy}>{t('issues.reject')}</Button>
                      <Button variant="secondary" onClick={() => void decide(selected.id, 'unresolved')} disabled={busy}>
                        {t('issues.markUnresolved')}
                      </Button>
                    </div>
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      }
    />
  )
}
