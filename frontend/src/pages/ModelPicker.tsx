import { useEffect, useRef, useState } from 'react'
import type { ModelInfo } from '../api'
import ModelDetails from './ModelDetails'
import { context, hasDetails, plain, price } from './modelFormat'

/** How many models are drawn at once: EdenAI lists over a thousand, each with a description. */
const PAGE = 50

function Row({ model, selected, onPick, onMore }: { model: ModelInfo; selected: boolean; onPick: () => void; onMore: (m: ModelInfo) => void }) {
  const hasPrice = model.input_per_million != null || model.output_per_million != null
  const free = model.input_per_million === 0 && model.output_per_million === 0
  const rich = hasPrice || model.description || model.context_length || model.name
  const priceClass = (value: number | null | undefined) => (value === 0 ? 'font-semibold text-emerald-700' : 'font-semibold text-slate-800')
  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={0}
      onClick={onPick}
      onKeyDown={(e) => e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onPick())}
      className={`flex cursor-pointer gap-3 border-b border-slate-100 px-3 py-2 last:border-b-0 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none ${
        selected ? 'bg-slate-50' : ''
      }`}
    >
      {hasPrice && (
        <div className="w-[5.5rem] shrink-0 border-r border-slate-100 pr-3 text-xs leading-5 text-slate-500">
          <div>
            In: <span className={priceClass(model.input_per_million)}>{price(model.input_per_million)}</span>
          </div>
          <div>
            Out: <span className={priceClass(model.output_per_million)}>{price(model.output_per_million)}</span>
          </div>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className={`break-all text-sm ${rich || selected ? 'font-semibold' : ''}`}>{model.id}</div>
        {model.name && <div className="break-words text-xs text-slate-500">{model.name}</div>}
        {(model.provider || model.context_length) && (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {model.provider && <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5">● {model.provider}</span>}
            {model.context_length ? <span>{context(model.context_length)} tokens context</span> : null}
          </div>
        )}
        {model.description && <p className="mt-1 line-clamp-2 whitespace-pre-line break-words text-xs text-slate-600">{plain(model.description)}</p>}
        {hasDetails(model) && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation() // opening the information must not pick the model
              onMore(model)
            }}
            className="text-xs text-slate-500 underline hover:text-slate-800"
          >
            {model.description ? 'Lees meer' : 'Meer info'}
          </button>
        )}
      </div>
      {free && <span className="shrink-0 text-xs font-medium text-emerald-700">Free</span>}
    </div>
  )
}

/**
 * A model dropdown as wide as its field, with a search box, and for endpoints that say so (OpenRouter, EdenAI) a card
 * per model: price per 1M tokens, provider, context length and a description of two lines with "Lees meer".
 * Providers list hundreds of long ids, which a native select shows narrow, cut off and without a way to search.
 */
export default function ModelPicker({
  value,
  models,
  emptyLabel,
  onChange,
}: {
  value: string
  models: ModelInfo[]
  /** Shown for "no model" (also the first entry of the list). */
  emptyLabel: string
  onChange: (model: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const [detail, setDetail] = useState<ModelInfo | null>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false)
    // Escape closes the information window first, then the list
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && (detail ? setDetail(null) : setOpen(false))
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, detail])

  const term = filter.trim().toLowerCase()
  const matches = term
    ? models.filter((m) => [m.id, m.name, m.provider].some((field) => field?.toLowerCase().includes(term)))
    : models
  const shown = matches.slice(0, limit)
  const priced = models.some((m) => m.input_per_million != null || m.output_per_million != null)
  const known = models.some((m) => m.id === value)
  const current = models.find((m) => m.id === value)

  const pick = (model: string) => {
    onChange(model)
    setOpen(false)
    setFilter('')
    setLimit(PAGE)
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-left text-sm"
      >
        <span className={`truncate ${value ? '' : 'text-slate-400'}`}>
          {value || emptyLabel}
          {current?.name && <span className="ml-2 text-xs text-slate-400">{current.name}</span>}
        </span>
        <span aria-hidden className="text-slate-400">
          ▾
        </span>
      </button>

      {detail && (
        <ModelDetails
          model={detail}
          selected={detail.id === value}
          onPick={() => {
            pick(detail.id)
            setDetail(null)
          }}
          onClose={() => setDetail(null)}
        />
      )}

      {open && (
        <div className="absolute left-0 right-0 z-30 mt-1 rounded-lg border border-slate-200 bg-white shadow-lg">
          <input
            autoFocus
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value)
              setLimit(PAGE)
            }}
            onKeyDown={(e) => e.key === 'Enter' && matches.length === 1 && pick(matches[0].id)}
            placeholder={`Zoek in ${models.length} modellen…`}
            aria-label="Zoek een model"
            className="w-full border-b border-slate-200 px-3 py-2 text-sm outline-none"
          />
          {priced && <p className="border-b border-slate-100 bg-slate-50 px-3 py-1 text-[11px] text-slate-500">Prijzen in USD per 1 miljoen tokens</p>}
          <div role="listbox" className="max-h-96 overflow-y-auto">
            {!term && (
              <div
                role="option"
                aria-selected={!value}
                tabIndex={0}
                onClick={() => pick('')}
                onKeyDown={(e) => e.key === 'Enter' && pick('')}
                className="cursor-pointer border-b border-slate-100 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-50"
              >
                {emptyLabel}
              </div>
            )}
            {value && !known && !term && (
              <Row model={{ id: value } as ModelInfo} selected onPick={() => pick(value)} onMore={setDetail} />
            )}
            {shown.map((m) => (
              <Row key={m.id} model={m} selected={m.id === value} onPick={() => pick(m.id)} onMore={setDetail} />
            ))}
            {matches.length > shown.length && (
              <button
                type="button"
                onClick={() => setLimit((l) => l + PAGE)}
                className="block w-full px-3 py-2 text-center text-xs text-slate-600 hover:bg-slate-50"
              >
                Toon {Math.min(PAGE, matches.length - shown.length)} meer ({matches.length - shown.length} niet getoond; zoek om te verfijnen)
              </button>
            )}
            {matches.length === 0 && <div className="px-3 py-2 text-sm text-slate-400">Geen model gevonden voor “{filter}”.</div>}
          </div>
        </div>
      )}
    </div>
  )
}
