import { Card } from '../components'
import { THEME_LABELS, useTheme, type ThemePreference } from '../theme'

const OPTIONS: { id: ThemePreference; blurb: string; swatches: string[] }[] = [
  { id: 'light', blurb: 'Het lichte, heldere scherm zoals Apollo altijd was.', swatches: ['#f1f5f9', '#ffffff', '#0f172a'] },
  {
    id: 'dark',
    blurb: 'Rustig en donker in het palet van Gaia: warm rookgrijs en saliegroen, met een zacht groen schijnsel dat langzaam beweegt.',
    swatches: ['#1a1916', '#2e2c26', '#3a503f', '#7c9a82', '#c7d7ca'],
  },
  { id: 'system', blurb: 'Donker of licht, zoals je computer is ingesteld.', swatches: ['#f1f5f9', '#1a1916'] },
]

/** Light, ambient (dark) or automatic. Remembered in this browser or app window. */
export default function AppearanceCard() {
  const [preference, choose] = useTheme()
  return (
    <Card>
      <h2 className="text-lg font-semibold">Weergave</h2>
      <p className="mt-1 text-sm text-slate-500">
        De schakelaar rechtsboven (☀︎ ☾ ◐) doet hetzelfde. Bij “Ambient” staat de beweging uit als je computer “minder beweging” vraagt.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Weergave">
        {OPTIONS.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={preference === o.id}
            onClick={() => choose(o.id)}
            className={`rounded border px-3 py-2 text-left text-sm ${
              preference === o.id ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'
            }`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="font-medium">{THEME_LABELS[o.id]}</span>
              <span className="flex">
                {o.swatches.map((c) => (
                  <span key={c} className="-ml-1 h-3.5 w-3.5 rounded-full border border-slate-300 first:ml-0" style={{ backgroundColor: c }} />
                ))}
              </span>
            </span>
            <span className="mt-1 block text-xs text-slate-500">{o.blurb}</span>
          </button>
        ))}
      </div>
    </Card>
  )
}
