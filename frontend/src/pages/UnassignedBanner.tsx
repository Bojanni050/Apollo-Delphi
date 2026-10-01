import { useCallback, useEffect, useState } from 'react'
import { api, type AdoptResult, type Unassigned } from '../api'
import { Button, Card, ErrorText } from '../components'

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** Offers to move everything that belongs to no werkmap (from before werkmappen existed) into the active one. */
export default function UnassignedBanner({
  workspaceId,
  workspaceName,
  onAdopted,
}: {
  workspaceId?: number | null
  workspaceName?: string | null
  onAdopted: () => void
}) {
  const [counts, setCounts] = useState<Unassigned | null>(null)
  const [result, setResult] = useState<AdoptResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setCounts(await api.unassigned())
    } catch {
      setCounts(null) // the banner is optional; never block the page on it
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, workspaceId])

  const adopt = async () => {
    if (!workspaceId || !counts) return
    const what = [
      plural(counts.documents, 'document', 'documenten'),
      counts.analysis_runs ? plural(counts.analysis_runs, 'analyse', 'analyses') : '',
      counts.generated_documents ? plural(counts.generated_documents, 'gegenereerd document', 'gegenereerde documenten') : '',
    ]
      .filter(Boolean)
      .join(', ')
    if (!window.confirm(`${what} onderbrengen in werkmap "${workspaceName}"?\n\nDit is niet terug te draaien vanuit de app.`)) return
    setBusy(true)
    setError(null)
    try {
      setResult(await api.adoptUnassigned(workspaceId))
      await load()
      onAdopted()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <Card className="border border-emerald-200 bg-emerald-50">
        <p className="text-sm text-emerald-900">
          Verplaatst naar <strong>{workspaceName}</strong>: {plural(result.documents, 'document', 'documenten')},{' '}
          {plural(result.analysis_runs, 'analyse', 'analyses')}, {plural(result.generated_documents, 'gegenereerd document', 'gegenereerde documenten')}.{' '}
          {result.mirrored_to_repository > 0 && `${plural(result.mirrored_to_repository, 'origineel', 'originelen')} in de repository gecommit.`}
        </p>
        {result.not_mirrored.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">
            {result.not_mirrored.map((n) => (
              <li key={n.document_id}>
                {n.filename}: niet in de repository gezet ({n.reason})
              </li>
            ))}
          </ul>
        )}
      </Card>
    )
  }

  if (!counts || counts.documents + counts.analysis_runs + counts.generated_documents === 0) return null

  return (
    <Card className="border border-amber-200 bg-amber-50">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-amber-900">
          <strong>{plural(counts.documents, 'document', 'documenten')}</strong> horen bij geen werkmap
          {counts.analysis_runs + counts.generated_documents > 0 &&
            ` (met ${plural(counts.analysis_runs, 'analyse', 'analyses')} en ${plural(counts.generated_documents, 'gegenereerd document', 'gegenereerde documenten')})`}
          .{' '}
          {workspaceId
            ? 'Ze zijn nu alleen zichtbaar zonder werkmap.'
            : 'Kies of maak eerst een werkmap om ze onder te brengen.'}
        </div>
        {workspaceId ? (
          <Button onClick={() => void adopt()} disabled={busy}>
            {busy ? 'Bezig…' : `Onderbrengen in “${workspaceName}”`}
          </Button>
        ) : null}
      </div>
      <ErrorText message={error} />
    </Card>
  )
}
