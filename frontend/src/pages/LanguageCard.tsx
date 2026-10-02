import { Card } from '../components'
import { useLang, useT, type Lang } from '../i18n'

const OPTIONS: { id: Lang; label: string }[] = [
  { id: 'nl', label: 'Nederlands' },
  { id: 'en', label: 'English' },
]

/** Dutch (the default) or English, remembered in this browser or app window. */
export default function LanguageCard({ onChoose }: { onChoose: (lang: Lang) => void }) {
  const active = useLang()
  const t = useT()
  return (
    <Card>
      <h2 className="text-lg font-semibold">{t('appearance.language')}</h2>
      <p className="mt-1 text-sm text-slate-500">{t('appearance.languageHint')}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t('appearance.language')}>
        {OPTIONS.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={active === o.id}
            onClick={() => onChoose(o.id)}
            className={`rounded-lg border px-3 py-2 text-left text-sm ${
              active === o.id ? 'border-slate-900 bg-slate-50 font-medium' : 'border-slate-200 hover:bg-slate-50'
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </Card>
  )
}
