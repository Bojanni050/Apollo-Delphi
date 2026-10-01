import { THEME_LABELS, useTheme, type ThemePreference } from '../theme'

const ORDER: ThemePreference[] = ['light', 'dark', 'system']
const ICON: Record<ThemePreference, string> = { light: '☀︎', dark: '☾', system: '◐' }

/** One button in the top bar that steps through light, ambient (dark) and automatic. */
export default function ThemeToggle() {
  const [preference, choose] = useTheme()
  const next = ORDER[(ORDER.indexOf(preference) + 1) % ORDER.length]
  return (
    <button
      type="button"
      onClick={() => choose(next)}
      title={`Weergave: ${THEME_LABELS[preference]}. Klik voor: ${THEME_LABELS[next]}`}
      aria-label={`Weergave: ${THEME_LABELS[preference]}. Klik voor ${THEME_LABELS[next]}`}
      className="rounded-lg border border-slate-200 px-2 py-1 text-sm text-slate-600 hover:bg-slate-50"
    >
      {ICON[preference]}
    </button>
  )
}
