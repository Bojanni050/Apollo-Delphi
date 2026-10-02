import type { ReactNode } from 'react'
import { hasKey, translate, useLang } from './i18n'

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
  return <span className={`inline-flex shrink-0 self-center items-center justify-center whitespace-nowrap px-2.5 py-0.5 rounded-full text-xs font-medium leading-5 ${styles[kind]}`}>{children}</span>
}

export function StatusBadge({ status }: { status: string }) {
  const lang = useLang()
  const key = `status.${status}`
  const label = hasKey(key) ? translate(lang, key) : status
  if (status === 'parsed')
    return (
      <span title={translate(lang, 'status.gelezen')}>
        <Badge kind="warn">{label}</Badge>
      </span>
    )
  const kind =
    status === 'indexed' || status === 'resolved' || status === 'completed' || status === 'confirmed'
      ? 'ok'
      : status === 'failed' || status === 'error' || status === 'disputed' || status === 'remaining_contradiction'
        ? 'err'
        : 'warn'
  return <Badge kind={kind}>{label}</Badge>
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
