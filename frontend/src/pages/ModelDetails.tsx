import type { ReactNode } from 'react'
import type { ModelInfo } from '../api'
import { FEATURES, MODALITIES, plain, price } from './modelFormat'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </section>
  )
}

function Chips({ items, empty }: { items: string[]; empty?: string }) {
  if (items.length === 0) return <span className="text-sm text-slate-400">{empty ?? 'Niet opgegeven'}</span>
  return (
    <span className="flex flex-wrap gap-1.5">
      {items.map((label) => (
        <span key={label} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs text-slate-700">
          {label}
        </span>
      ))}
    </span>
  )
}

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 py-1 text-sm">
      <dt className="w-32 shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-slate-800">{children}</dd>
    </div>
  )
}

const tokens = (n: number) => `${n.toLocaleString('nl-NL')} tokens`

/** Everything an endpoint says about one model: description, what it can take in and give out, features, price, limits. */
export default function ModelDetails({
  model,
  selected,
  onPick,
  onClose,
}: {
  model: ModelInfo
  selected: boolean
  onPick: () => void
  onClose: () => void
}) {
  const modalities = (list: string[]) => list.map((m) => MODALITIES[m] ?? m)
  const features = (model.features ?? []).map((f) => FEATURES[f] ?? f)
  const knownCapabilities = (model.input_modalities?.length ?? 0) + (model.output_modalities?.length ?? 0) + features.length > 0
  const prices: [string, number | null | undefined][] = [
    ['Invoer (input)', model.input_per_million],
    ['Uitvoer (output)', model.output_per_million],
    ['Cache lezen', model.cache_read_per_million],
    ['Cache schrijven', model.cache_write_per_million],
  ]
  const knownPrices = prices.filter(([, value]) => value != null)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-label={`Modelinformatie ${model.id}`} className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-xl">
        <div className="overflow-y-auto p-5">
          <h2 className="break-all text-lg font-semibold text-slate-900">{model.id}</h2>
          {model.name && <p className="text-sm text-slate-500">{model.name}</p>}
          {model.provider && (
            <span className="mt-2 inline-block rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs text-slate-600">● {model.provider}</span>
          )}

          {model.description && (
            <Section title="Beschrijving">
              <p className="whitespace-pre-line break-words text-sm leading-relaxed text-slate-700">{plain(model.description)}</p>
            </Section>
          )}

          <Section title="Mogelijkheden">
            {knownCapabilities ? (
              <dl>
                <Line label="Invoer">
                  <Chips items={modalities(model.input_modalities ?? [])} />
                </Line>
                <Line label="Uitvoer">
                  <Chips items={modalities(model.output_modalities ?? [])} />
                </Line>
                <Line label="Functies">
                  <Chips items={features} empty="Geen bijzondere functies opgegeven" />
                </Line>
              </dl>
            ) : (
              <p className="text-sm text-slate-400">Dit endpoint geeft niet door wat het model kan.</p>
            )}
          </Section>

          <Section title="Kosten per 1 miljoen tokens (USD)">
            {knownPrices.length > 0 ? (
              <dl>
                {knownPrices.map(([label, value]) => (
                  <Line key={label} label={label}>
                    <span className={value === 0 ? 'font-semibold text-emerald-700' : 'font-semibold'}>{price(value)}</span>
                  </Line>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-slate-400">Geen prijzen opgegeven.</p>
            )}
          </Section>

          {(model.context_length || model.max_output_tokens) && (
            <Section title="Limieten">
              <dl>
                {model.context_length ? <Line label="Contextvenster">{tokens(model.context_length)}</Line> : null}
                {model.max_output_tokens ? <Line label="Maximale uitvoer">{tokens(model.max_output_tokens)}</Line> : null}
              </dl>
            </Section>
          )}

          {(model.regions?.length > 0 || model.created) && (
            <Section title="Overig">
              <dl>
                {model.regions?.length > 0 && <Line label="Regio’s">{model.regions.join(', ')}</Line>}
                {model.created ? <Line label="Toegevoegd">{new Date(model.created * 1000).toLocaleDateString('nl-NL')}</Line> : null}
              </dl>
            </Section>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 p-4">
          <button type="button" onClick={onClose} className="rounded-lg bg-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-300">
            Sluiten
          </button>
          <button
            type="button"
            onClick={onPick}
            disabled={selected}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {selected ? 'Dit model is gekozen' : 'Dit model kiezen'}
          </button>
        </div>
      </div>
    </div>
  )
}
