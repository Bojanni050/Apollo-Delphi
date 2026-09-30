import { useEffect, useState } from 'react'
import { api, type GeneratedDocument, type VerificationFinding } from '../api'
import { Button, Card, ErrorText, StatusBadge } from '../components'

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(res.statusText)
  return res.json() as Promise<T>
}

function renderMarkdown(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-4">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-semibold mt-2">$1</h1>')
    .replace(/^- (.+)$/gm, '<li class="ml-5 list-disc">$1</li>')
    .replace(/\n{2,}/g, '<br/><br/>')
}

export default function GeneratedPage() {
  const [docs, setDocs] = useState<GeneratedDocument[]>([])
  const [selected, setSelected] = useState<GeneratedDocument | null>(null)
  const [findings, setFindings] = useState<VerificationFinding[]>([])
  const [title, setTitle] = useState('Synthesized Report')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDocs = async () => {
    const res = await fetch('/api/documents/generated/list').catch(() => null)
    if (res && res.ok) setDocs(await res.json())
  }

  useEffect(() => {
    void loadDocs().catch(() => setError('Could not load generated documents'))
  }, [])

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      const doc = await api.generateDocument(title)
      setSelected(doc)
      setFindings(await api.getVerification(doc.id))
      await loadDocs()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const select = async (id: number) => {
    setError(null)
    try {
      setSelected(await fetchJson<GeneratedDocument>(`/api/documents/generated/${id}`))
      setFindings(await api.getVerification(id))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="grid grid-cols-[320px,1fr] gap-6">
      <Card>
        <h2 className="font-semibold mb-3">Generate</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full border rounded px-2 py-1.5 text-sm mb-2"
          placeholder="Report title"
        />
        <Button onClick={() => void generate()} disabled={busy}>
          {busy ? 'Generating…' : 'Generate from knowledge state'}
        </Button>
        <ErrorText message={error} />
        <h3 className="font-semibold mt-5 mb-2 text-sm">History</h3>
        <ul className="space-y-1 text-sm">
          {docs.map((d) => (
            <li key={d.id}>
              <button
                onClick={() => void select(d.id)}
                className={`w-full text-left p-2 rounded border ${
                  selected?.id === d.id ? 'border-slate-900 bg-slate-50' : 'hover:bg-slate-50'
                }`}
              >
                <div className="flex justify-between items-center gap-2">
                  <span className="font-medium line-clamp-1">{d.title}</span>
                  <StatusBadge status={d.verification_status} />
                </div>
                <span className="text-xs text-slate-400">{new Date(d.created_at).toLocaleString()}</span>
              </button>
            </li>
          ))}
          {docs.length === 0 && <li className="text-slate-400">No generated documents yet.</li>}
        </ul>
      </Card>

      <div className="space-y-4">
        {selected ? (
          <>
            <Card>
              <div className="flex justify-between items-center">
                <h2 className="text-lg font-semibold">{selected.title}</h2>
                <div className="flex gap-2 items-center">
                  <StatusBadge status={selected.status} />
                  <StatusBadge status={selected.verification_status} />
                </div>
              </div>
              <div
                className="prose prose-sm mt-3 text-sm"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(selected.content ?? '') }}
              />
            </Card>
            <Card>
              <h3 className="font-semibold mb-2">Verification findings ({findings.length})</h3>
              <ul className="space-y-2 text-sm">
                {findings.map((f) => (
                  <li key={f.id} className="border rounded p-2">
                    <div className="flex justify-between">
                      <span className="font-medium">{f.finding_type}</span>
                      <StatusBadge status={f.severity} />
                    </div>
                    {f.statement && <p className="text-slate-600 mt-1">{f.statement}</p>}
                    {f.expected && <p className="text-slate-500 text-xs mt-1">Expected: {f.expected}</p>}
                    {f.recommendation && <p className="text-slate-500 text-xs mt-1">{f.recommendation}</p>}
                  </li>
                ))}
                {findings.length === 0 && <li className="text-slate-400">No findings.</li>}
              </ul>
            </Card>
          </>
        ) : (
          <Card>
            <p className="text-slate-400 text-sm">
              Generate a document from the resolved knowledge state. Requires a built knowledge state (run analysis and build knowledge first).
            </p>
          </Card>
        )}
      </div>
    </div>
  )
}
