import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card bg-white rounded-2xl border border-slate-200 shadow-sm p-5 ${className}`}>{children}</div>
}

export function Badge({ kind, children }: { kind: 'ok' | 'warn' | 'err' | 'neutral'; children: ReactNode }) {
  const styles = {
    ok: 'bg-emerald-100 text-emerald-800',
    warn: 'bg-amber-100 text-amber-800',
    err: 'bg-red-100 text-red-800',
    neutral: 'bg-slate-200 text-slate-700',
  } as const
  return <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[kind]}`}>{children}</span>
}

export function StatusBadge({ status }: { status: string }) {
  if (status === 'parsed')
    return (
      <span title="Gelezen: het document is te lezen en te doorzoeken op woorden. Het embedden (zoeken op betekenis) loopt nog of wacht.">
        <Badge kind="warn">gelezen</Badge>
      </span>
    )
  if (status === 'indexed' || status === 'resolved' || status === 'completed' || status === 'confirmed')
    return <Badge kind="ok">{status}</Badge>
  if (status === 'failed' || status === 'error' || status === 'disputed' || status === 'remaining_contradiction')
    return <Badge kind="err">{status}</Badge>
  return <Badge kind="warn">{status}</Badge>
}

export function Button({
  children,
  onClick,
  disabled,
  variant = 'primary',
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'secondary' | 'danger'
}) {
  const styles = {
    primary: 'bg-slate-900 text-white hover:bg-slate-700',
    secondary: 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50',
    danger: 'bg-red-600 text-white hover:bg-red-500',
  } as const
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles[variant]}`}
    >
      {children}
    </button>
  )
}

export function ErrorText({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="text-sm text-red-600 mt-2">{message}</p>
}
