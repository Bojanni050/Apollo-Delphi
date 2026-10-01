import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

/**
 * What the reading pane should show: a document, and optionally the place in it that matters (a fragment, lines, a quote).
 * Any page can open it: a search hit, a citation, a piece of evidence, a document in the list.
 */
export type ReaderTarget = {
  documentId: number
  /** A fragment of the document: its lines are looked up in the text. The most precise way to point. */
  chunkId?: number | null
  lineStart?: number | null
  lineEnd?: number | null
  page?: number | null
  /** A quote: found in the text when there are no lines (evidence, an old index). */
  excerpt?: string | null
  /** The search words, marked in the text. */
  query?: string | null
  /** Changes with every request, so asking for the same place again scrolls there again. */
  nonce: number
}

type ReaderState = {
  target: ReaderTarget | null
  isOpen: boolean
  open: (target: Omit<ReaderTarget, 'nonce'>) => void
  close: () => void
  toggle: () => void
}

const ReaderContext = createContext<ReaderState | null>(null)

export function ReaderProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<ReaderTarget | null>(null)
  const [isOpen, setOpen] = useState(false)
  const nonce = useRef(0)

  const open = useCallback((next: Omit<ReaderTarget, 'nonce'>) => {
    setTarget({ ...next, nonce: ++nonce.current })
    setOpen(true)
  }, [])
  const close = useCallback(() => setOpen(false), [])
  const toggle = useCallback(() => setOpen((o) => !o), [])

  const value = useMemo(() => ({ target, isOpen, open, close, toggle }), [target, isOpen, open, close, toggle])
  return <ReaderContext.Provider value={value}>{children}</ReaderContext.Provider>
}

/** Open things in the reading pane. Outside the app shell (nothing to open it in) the calls do nothing. */
export function useReader(): ReaderState {
  return (
    useContext(ReaderContext) ?? { target: null, isOpen: false, open: () => undefined, close: () => undefined, toggle: () => undefined }
  )
}
