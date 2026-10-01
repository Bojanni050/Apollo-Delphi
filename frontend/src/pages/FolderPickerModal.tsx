import { useEffect, useRef, useState } from 'react'
import { api, type FolderBrowse } from '../api'
import { Button, ErrorText } from '../components'

/** Pick a folder on the machine the backend runs on. Calls ``onSelect`` with an absolute path. */
export default function FolderPickerModal({
  initialPath,
  title = 'Kies een map',
  onSelect,
  onClose,
}: {
  initialPath?: string
  title?: string
  onSelect: (path: string) => void
  onClose: () => void
}) {
  const [data, setData] = useState<FolderBrowse | null>(null)
  const [typed, setTyped] = useState(initialPath ?? '')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // A slow answer must not overwrite a newer navigation.
  const latest = useRef(0)

  const open = async (path?: string) => {
    const seq = ++latest.current
    setLoading(true)
    setError(null)
    try {
      const res = await api.browseFolders(path)
      if (seq !== latest.current) return
      setData(res)
      setTyped(res.current_path)
    } catch (e) {
      if (seq === latest.current) setError((e as Error).message)
    } finally {
      if (seq === latest.current) setLoading(false)
    }
  }

  useEffect(() => {
    void open(initialPath?.trim() || undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const chip = 'rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-label={title} className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-lg bg-white shadow-xl">
        <div className="border-b border-slate-200 p-4">
          <h2 className="font-semibold text-slate-900">{title}</h2>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              void open(typed)
            }}
          >
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              spellCheck={false}
              aria-label="Pad"
              className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1.5 font-mono text-xs"
            />
            <Button variant="secondary" onClick={() => void open(typed)} disabled={loading}>
              Ga
            </Button>
          </form>
          {data && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.quick_access.map((q) => (
                <button key={q.path} type="button" className={chip} onClick={() => void open(q.path)}>
                  {q.name}
                </button>
              ))}
              {data.drives.map((d) => (
                <button key={d} type="button" className={chip} onClick={() => void open(d)}>
                  {d}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="min-h-[12rem] flex-1 overflow-y-auto p-2">
          {data?.parent_path && (
            <button
              type="button"
              onClick={() => void open(data.parent_path ?? undefined)}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50"
            >
              <span aria-hidden>↑</span> Een map omhoog
            </button>
          )}
          {data?.folders.map((f) => (
            <button
              key={f.path}
              type="button"
              onClick={() => void open(f.path)}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50"
            >
              <span aria-hidden className="text-slate-400">
                📁
              </span>
              <span className="truncate">{f.name}</span>
            </button>
          ))}
          {data && data.folders.length === 0 && !loading && (
            <p className="px-2 py-3 text-sm text-slate-400">Geen submappen.</p>
          )}
          {data?.truncated && (
            <p className="px-2 py-2 text-xs text-slate-400">Alleen de eerste mappen worden getoond; typ het pad zelf.</p>
          )}
          {loading && !data && <p className="px-2 py-3 text-sm text-slate-400">Laden…</p>}
          <ErrorText message={error} />
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-200 p-4">
          <span className="min-w-0 truncate font-mono text-xs text-slate-500" title={data?.current_path}>
            {data?.current_path ?? ''}
          </span>
          <div className="flex shrink-0 gap-2">
            <Button variant="secondary" onClick={onClose}>
              Annuleren
            </Button>
            <Button onClick={() => data && onSelect(data.current_path)} disabled={!data || loading}>
              Deze map kiezen
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
