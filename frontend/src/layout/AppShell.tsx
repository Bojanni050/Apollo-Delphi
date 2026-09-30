import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

export type NavItem = { id: string; label: string; icon?: ReactNode }

type AppShellProps = {
  nav: NavItem[]
  active: string
  onNavigate: (id: string) => void
  breadcrumb: ReactNode
  topActions?: ReactNode
  contextTitle?: string
  contextPane?: ReactNode
  children: ReactNode
}

export default function AppShell({
  nav,
  active,
  onNavigate,
  breadcrumb,
  topActions,
  contextTitle,
  contextPane,
  children,
}: AppShellProps) {
  // Left expanded by default, right collapsed by default (contextual)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightOpen, setRightOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 text-slate-800">
      {/* 1st column: left sidebar, collapsible, expanded by default */}
      <aside
        className={`flex shrink-0 flex-col border-r border-slate-200 bg-white transition-[width] duration-200 ${
          leftCollapsed ? 'w-14' : 'w-60'
        }`}
      >
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-slate-900 text-sm font-bold text-white">
            A
          </div>
          {!leftCollapsed && (
            <>
              <span className="truncate text-sm font-semibold">Apollo</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">Free</span>
              <button
                onClick={() => setLeftCollapsed(true)}
                title="Collapse sidebar"
                className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                ⇤
              </button>
            </>
          )}
          {leftCollapsed && (
            <button
              onClick={() => setLeftCollapsed(false)}
              title="Expand sidebar"
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              ⇥
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-3">
          {!leftCollapsed && <p className="px-2 text-[11px] uppercase tracking-wide text-slate-400">Project</p>}
          {!leftCollapsed && (
            <button className="mt-1 flex w-full items-center gap-1 rounded px-2 py-1.5 text-left text-sm font-medium hover:bg-slate-100">
              <span className="truncate">AS Production</span>
              <span className="ml-auto text-slate-400">⇅</span>
            </button>
          )}

          <nav className="mt-3 space-y-0.5">
            {nav.map((n) => (
              <button
                key={n.id}
                onClick={() => onNavigate(n.id)}
                title={leftCollapsed ? n.label : undefined}
                className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm ${
                  active === n.id
                    ? 'bg-slate-100 font-medium text-slate-900'
                    : 'text-slate-600 hover:bg-slate-50'
                } ${leftCollapsed ? 'justify-center' : ''}`}
              >
                <span className="w-5 shrink-0 text-center text-slate-400">{n.icon ?? '•'}</span>
                {!leftCollapsed && <span className="truncate">{n.label}</span>}
              </button>
            ))}
          </nav>

          {!leftCollapsed && (
            <>
              <p className="mt-6 px-2 text-[11px] uppercase tracking-wide text-slate-400">Quick access</p>
              <div className="mt-1 space-y-0.5 text-sm text-slate-600">
                {['API key', 'Setup for agents', 'Invite members', 'Resources', 'Help', 'Settings'].map((l) => (
                  <div key={l} className="rounded px-2 py-1.5 hover:bg-slate-50">
                    {l}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {!leftCollapsed && (
          <div className="border-t border-slate-200 p-2">
            <div className="flex items-center justify-between rounded border px-2 py-2 text-sm">
              <span className="text-slate-600">Usage ›</span>
              <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-white">Upgrade</span>
            </div>
            <div className="mt-2 flex items-center gap-2 px-2 py-1 text-xs text-slate-500">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-200">U</span>
              <span className="truncate">user@example.com</span>
            </div>
          </div>
        )}
      </aside>

      {/* Center: topbar + content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-4">
          <button
            onClick={() => setLeftCollapsed((v) => !v)}
            title="Toggle left sidebar"
            className="rounded border border-slate-200 px-2 py-1 text-sm text-slate-500 hover:bg-slate-50"
          >
            {leftCollapsed ? '»' : '«'}
          </button>
          <div className="min-w-0 flex-1 truncate text-sm text-slate-500">{breadcrumb}</div>
          {topActions && <div className="flex shrink-0 items-center gap-2">{topActions}</div>}
          <button
            onClick={() => setRightOpen((v) => !v)}
            title={rightOpen ? 'Collapse context panel' : 'Open context panel'}
            className={`shrink-0 rounded border px-2 py-1 text-sm ${
              rightOpen
                ? 'border-slate-900 bg-slate-900 text-white'
                : 'border-slate-200 text-slate-500 hover:bg-slate-50'
            }`}
          >
            {rightOpen ? '⇥' : '⇤'} <span className="hidden sm:inline">Context</span>
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          {/* Main content (2nd + 3rd columns live inside children via SplitView) */}
          <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>

          {/* 4th column: right contextual sidebar, collapsed by default */}
          {rightOpen ? (
            <aside className="flex w-80 shrink-0 flex-col border-l border-slate-200 bg-white xl:w-96">
              <div className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 px-4">
                <h2 className="truncate text-sm font-semibold">{contextTitle ?? 'Context'}</h2>
                <button
                  onClick={() => setRightOpen(false)}
                  title="Collapse"
                  className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                >
                  ✕
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-4">{contextPane ?? <EmptyContext />}</div>
            </aside>
          ) : (
            <div
              title="Open context panel"
              onClick={() => setRightOpen(true)}
              className="flex w-8 shrink-0 cursor-pointer flex-col items-center border-l border-slate-200 bg-white py-3 text-slate-300 hover:bg-slate-50 hover:text-slate-500"
            >
              <span className="text-sm">‹</span>
              <span className="mt-2 text-[11px] font-medium [writing-mode:vertical-rl]">
                {contextTitle ?? 'Context'}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function EmptyContext() {
  return <p className="text-sm text-slate-400">Select an item to see contextual details here.</p>
}

/* ------------------------------------------------------------------ */
/* Resizable two-pane view: 2nd column adjustable, max half of screen  */
/* ------------------------------------------------------------------ */

export function SplitView({
  listPane,
  detailPane,
  initialWidth = 320,
  minWidth = 240,
}: {
  listPane: ReactNode
  detailPane: ReactNode
  initialWidth?: number
  minWidth?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(initialWidth)
  const draggingRef = useRef(false)

  const maxWidth = useCallback(() => {
    // max half of the screen
    const total = containerRef.current?.clientWidth ?? window.innerWidth
    return Math.floor(total / 2)
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const next = e.clientX - rect.left
      setWidth(Math.min(Math.max(next, minWidth), maxWidth()))
    }
    const onUp = () => {
      draggingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [minWidth, maxWidth])

  // clamp on resize so it never exceeds half screen
  useEffect(() => {
    const onResize = () => setWidth((w) => Math.min(Math.max(w, minWidth), maxWidth()))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [minWidth, maxWidth])

  // collapse helper for small screens
  const [listCollapsed, setListCollapsed] = useState(false)
  const effectiveWidth = listCollapsed ? 0 : width

  return (
    <div ref={containerRef} className="flex min-h-0 flex-1">
      {/* 2nd column */}
      {!listCollapsed && (
        <section
          style={{ width: effectiveWidth }}
          className="flex min-h-0 shrink-0 flex-col border-r border-slate-200 bg-white"
        >
          <div className="min-h-0 flex-1 overflow-y-auto">{listPane}</div>
        </section>
      )}

      {/* drag handle */}
      {!listCollapsed && (
        <div
          role="separator"
          aria-orientation="vertical"
          title="Drag to resize (max 50%)"
          onMouseDown={() => {
            draggingRef.current = true
            document.body.style.cursor = 'col-resize'
            document.body.style.userSelect = 'none'
          }}
          onDoubleClick={() => setWidth(initialWidth)}
          className="group relative w-1.5 shrink-0 cursor-col-resize bg-slate-100 hover:bg-slate-300"
        >
          <button
            onClick={(e) => {
              e.stopPropagation()
              setListCollapsed(true)
            }}
            title="Collapse list column"
            className="absolute top-1/2 left-1/2 hidden -translate-x-1/2 -translate-y-1/2 rounded-full border border-slate-300 bg-white px-1 text-[10px] text-slate-500 group-hover:block"
          >
            «
          </button>
        </div>
      )}

      {/* 3rd column: detail */}
      <section className="flex min-w-0 flex-1 flex-col bg-slate-50">
        {listCollapsed && (
          <div className="border-b border-slate-200 bg-white px-3 py-1">
            <button
              onClick={() => setListCollapsed(false)}
              className="rounded border border-slate-200 px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-50"
            >
              » Show list
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{detailPane}</div>
      </section>
    </div>
  )
}
