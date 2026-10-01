import { useEffect, useId, type ReactNode } from 'react'

/**
 * A dialog in the middle of the screen, in the app's own style. Use this instead of the browser's own popups
 * (window.confirm, the "upload N files to this site?" prompt): those cannot be moved or styled.
 */
export default function Modal({
  title,
  children,
  footer,
  onClose,
  width = 'max-w-md',
}: {
  title: string
  children: ReactNode
  footer?: ReactNode
  /** Escape and a click on the backdrop call this. Leave it out for a dialog that must be answered with a button. */
  onClose?: () => void
  /** A Tailwind max-width class. */
  width?: string
}) {
  const titleId = useId()

  useEffect(() => {
    if (!onClose) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(e) => onClose && e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`flex max-h-[85vh] w-full ${width} flex-col rounded-lg bg-white shadow-xl`}
      >
        <div className="overflow-y-auto p-5">
          <h2 id={titleId} className="text-lg font-semibold text-slate-900">
            {title}
          </h2>
          <div className="mt-2 text-sm text-slate-600">{children}</div>
        </div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-200 p-4">{footer}</div>}
      </div>
    </div>
  )
}
