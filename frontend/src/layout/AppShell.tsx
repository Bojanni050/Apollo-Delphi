import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import ReadingPane from '../components/ReadingPane'
import ThemeToggle from '../components/ThemeToggle'
import { ReaderProvider, useReader } from '../reader'
import { BUILD_TIME, BUILD_VERSION } from '../version'

/** One step of the working order shown in the top bar (Importeren, Delphi Pulse, Analyse). */
export type FlowStep = {
  id: string
  label: string
  /** The step has been taken: a check mark in front of it. */
  done?: boolean
  /** Cannot be opened yet; `title` says why. */
  disabled?: boolean
  title?: string
}

/** `dividerAfter`: a line under this item. `disabled` items cannot be opened yet; `title` says why. */
export type NavItem = { id: string; label: string; icon?: ReactNode; dividerAfter?: boolean; busy?: boolean; disabled?: boolean; title?: string }

type AppShellProps = {
  nav: NavItem[]
  active: string
  onNavigate: (id: string) => void
  breadcrumb: ReactNode
  topActions?: ReactNode
  /** The steps in the order the work is done; a click on one opens that page. */
  flow?: FlowStep[]
  contextTitle?: string
  contextPane?: ReactNode
  workspaceBar?: ReactNode
  children: ReactNode
}

/** The application frame: sidebar, page, reading pane (opened from search hits, citations, evidence) and context column. */
export default function AppShell(props: AppShellProps) {
  return (
    <ReaderProvider>
      <Shell {...props} />
    </ReaderProvider>
  )
}

function Shell({
  nav,
  active,
  onNavigate,
  breadcrumb,
  topActions,
  flow,
  contextTitle,
  contextPane,
  workspaceBar,
  children,
}: AppShellProps) {
  // Left expanded by default, right collapsed by default (contextual)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightOpen, setRightOpen] = useState(false)
  // The panel is put in the page first and faded in a moment later (so there is something to fade from), and stays in the
  // page while it slides shut: `panelMounted` is whether it is there, `panelShown` whether it is visible.
  const [panelMounted, setPanelMounted] = useState(false)
  const [panelShown, setPanelShown] = useState(false)
  useEffect(() => {
    if (rightOpen) {
      setPanelMounted(true)
      const timer = window.setTimeout(() => setPanelShown(true), 20)
      return () => window.clearTimeout(timer)
    }
    setPanelShown(false)
    const timer = window.setTimeout(() => setPanelMounted(false), 350)
    return () => window.clearTimeout(timer)
  }, [rightOpen])
  const reader = useReader()

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100 text-slate-800">
      {/* 1st column: left sidebar, collapsible, expanded by default */}
      <aside
        className={`flex shrink-0 flex-col transition-[width] duration-200 ${
          leftCollapsed ? 'w-14' : 'w-60'
        }`}
      >
        <div className="flex h-14 items-center gap-2 px-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-sm font-bold text-white">
            A
          </div>
          {!leftCollapsed && (
            <>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold">Apollo</div>
                <div className="truncate text-[11.4px] text-slate-400" title={`Build ${BUILD_VERSION}, ${BUILD_TIME}`}>
                  build {BUILD_VERSION} · {BUILD_TIME}
                </div>
              </div>
              <button
                onClick={() => setLeftCollapsed(true)}
                title="Collapse sidebar"
                className="ml-auto rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                ⇤
              </button>
            </>
          )}
          {leftCollapsed && (
            <button
              onClick={() => setLeftCollapsed(false)}
              title="Expand sidebar"
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              ⇥
            </button>
          )}
        </div>

        {/* Workspace bar: current werkmap name + create new */}
        {workspaceBar && !leftCollapsed && (
          <div className="px-3 pb-2">{workspaceBar}</div>
        )}

        <div className="flex-1 overflow-y-auto px-2 py-3">
          <nav className="mt-1 space-y-0.5">
            {nav.map((n) => (
              <div key={n.id}>
                <button
                  onClick={() => onNavigate(n.id)}
                  disabled={n.disabled}
                  title={n.disabled ? n.title : leftCollapsed ? n.label : undefined}
                  className={`flex w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent ${
                    active === n.id
                      ? 'border-slate-200 bg-white font-medium text-slate-900 shadow-sm'
                      : 'border-transparent text-slate-600 hover:bg-slate-200'
                  } ${leftCollapsed ? 'justify-center' : ''}`}
                >
                  <span className={`flex w-5 shrink-0 items-center justify-center text-center text-slate-400 ${n.busy ? 'nav-busy' : ''}`}>{n.icon ?? '•'}</span>
                  {!leftCollapsed && <span className={`truncate ${n.busy ? 'nav-busy' : ''}`}>{n.label}</span>}
                </button>
                {n.dividerAfter && <hr className="my-2 border-slate-200" />}
              </div>
            ))}
          </nav>
        </div>
      </aside>

      {/* Center: topbar + content */}
      <div className="my-2 mr-2 flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-4">
          <button
            onClick={() => setLeftCollapsed((v) => !v)}
            title="Toggle left sidebar"
            className="rounded-lg border border-slate-200 px-2 py-1 text-sm text-slate-500 hover:bg-slate-50"
          >
            {leftCollapsed ? '»' : '«'}
          </button>
          {flow && flow.length > 0 && (
            <nav aria-label="Werkwijze" className="hidden shrink-0 items-center gap-1 lg:flex">
              {flow.map((step, i) => (
                <Fragment key={step.id}>
                  {i > 0 && <span aria-hidden="true" className="text-slate-300">›</span>}
                  <button
                    type="button"
                    onClick={() => onNavigate(step.id)}
                    disabled={step.disabled}
                    title={step.title}
                    aria-current={active === step.id ? 'step' : undefined}
                    className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      active === step.id
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 text-slate-600 hover:bg-slate-50 disabled:hover:bg-transparent'
                    }`}
                  >
                    <span className="text-xs opacity-70">{step.done ? '✓' : i + 1}</span>
                    {step.label}
                  </button>
                </Fragment>
              ))}
            </nav>
          )}
          <div className="min-w-0 flex-1 truncate text-sm text-slate-500">{breadcrumb}</div>
          {topActions && <div className="flex shrink-0 items-center gap-2">{topActions}</div>}
          <ThemeToggle />
          <button
            onClick={reader.toggle}
            title={reader.isOpen ? 'Leesvenster sluiten' : 'Leesvenster openen'}
            aria-pressed={reader.isOpen}
            className={`shrink-0 rounded-lg border px-2 py-1 text-sm ${
              reader.isOpen ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-500 hover:bg-slate-50'
            }`}
          >
            ▤ <span className="hidden sm:inline">Lezen</span>
          </button>
          <button
            onClick={() => setRightOpen((v) => !v)}
            title={rightOpen ? 'Collapse context panel' : 'Open context panel'}
            className={`shrink-0 rounded-lg border px-2 py-1 text-sm ${
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
          <main className="flex min-w-[240px] flex-1 flex-col overflow-hidden">{children}</main>

          {/* Reading pane: a document in full, in front of the context column */}
          {reader.isOpen && <ReadingPane />}

          {/* 4th column: right contextual sidebar. The narrow strip with its title is always there (its arrow opens and
              closes the panel); the panel slides open to the left of it and pushes the reading pane and the page along. */}
          <div className="flex shrink-0">
            <div
              className={`relative shrink-0 overflow-hidden border-l border-slate-200 bg-white transition-[width] duration-300 ease-out motion-reduce:transition-none ${
                rightOpen ? 'w-80 xl:w-96' : 'w-0 border-l-0'
              }`}
            >
              {panelMounted && (
                <aside
                  aria-hidden={!rightOpen}
                  {...(rightOpen ? {} : ({ inert: '' } as object))}
                  className={`absolute inset-y-0 right-0 flex w-80 flex-col bg-white transition-opacity duration-200 motion-reduce:transition-none xl:w-96 ${
                    panelShown ? 'opacity-100 delay-100' : 'pointer-events-none opacity-0'
                  }`}
                >
                  <div className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-200 px-4">
                    <h2 className="truncate text-sm font-semibold">{contextTitle ?? 'Context'}</h2>
                  </div>
                  <div className="min-h-0 flex-1 overflow-y-auto p-4">{contextPane ?? <EmptyContext />}</div>
                </aside>
              )}
            </div>
            <button
              type="button"
              title={rightOpen ? 'Close context panel' : 'Open context panel'}
              aria-expanded={rightOpen}
              onClick={() => setRightOpen((v) => !v)}
              className="flex w-8 shrink-0 cursor-pointer flex-col items-center border-l border-slate-200 bg-white py-3 text-slate-300 hover:bg-slate-50 hover:text-slate-500"
            >
              <span className="text-sm">{rightOpen ? '›' : '‹'}</span>
              <span className="mt-2 text-[12.6px] font-medium [writing-mode:vertical-rl]">{contextTitle ?? 'Context'}</span>
            </button>
          </div>
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
            className="absolute top-1/2 left-1/2 hidden -translate-x-1/2 -translate-y-1/2 rounded-full border border-slate-300 bg-white px-1 text-[11.4px] text-slate-500 group-hover:block"
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
              className="rounded-lg border border-slate-200 px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-50"
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
