import { useEffect, useState } from 'react'
import { Card } from '../components'

const STORAGE_KEY = 'apollo.foundation-checklist.v1'

/** The working order for a new version of a foundation document (or any synthesis of the werkmap).
 * The ticks are kept per browser, so the list survives a reload and a restart. */
const STEPS: { title: string; detail: string }[] = [
  {
    title: 'Verzamel alles wat er is',
    detail:
      'Zet alle bestaande documenten in één werkmap (Inbox/, met de mapstructuur van Gaia erin, zoals Gaia/foundation/…). Ook oudere versies: daarin zie je wat eerder bedacht én laten vallen is. Verwijder niets — de analyse heeft de conflicten nodig om eerlijk te kunnen wegen.',
  },
  {
    title: 'Draai Delphi Pulse',
    detail:
      'Pulse stelt thema\u2019s, groepen en verbanden voor (met een groep foundation). Accepteer de voorstellen die kloppen, zodat de foundation-documenten bij elkaar komen te staan \u2014 ook als ze verspreid stonden.',
  },
  {
    title: 'Analyseer de foundation-groep',
    detail:
      'De analyse leest claims uit de documenten en houdt ze tegen het licht. Loop in Issues de tegenstrijdigheden na (met het groepen-filter): welke zijn in nieuwere documenten al opgelost, welke zijn nog echt open?',
  },
  {
    title: 'Denk met Delphi mee',
    detail:
      'Open het Delphi-bolletje en vraag: \u201cWat zegt de huidige collectie over het fundament van Gaia? Waar spreken de documenten elkaar tegen en wat is de beste oplossing?\u201d Zij filosofeert mee en blijft binnen de werkmap.',
  },
  {
    title: 'Laat Delphi het document schrijven',
    detail:
      'Snelst: laat haar het fundament uitleggen en zeg \u201cJa\u201d op haar aanbod om er een oracle van te maken (komt in Oracles/). Grondigst: Generate from knowledge state op de Generated-pagina \u2014 gebaseerd op alle uitgelezen claims, met verificatie eroverheen.',
  },
  {
    title: 'Zet het resultaat terug als nieuwe versie',
    detail:
      'Hernoem het resultaat naar bijvoorbeeld Gaia/foundation/foundation-v2.md. De oude versies blijven ernaast bestaan: de mapstructuur van Gaia blijft intact en git houdt de versiegeschiedenis bij.',
  },
]

export default function FoundationChecklist() {
  const [done, setDone] = useState<Set<number>>(new Set())
  const [open, setOpen] = useState(true)

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) setDone(new Set(JSON.parse(raw) as number[]))
    } catch {
      /* no saved state: start with a clean list */
    }
  }, [])

  const toggle = (i: number) => {
    setDone((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]))
      } catch {
        /* saving is nice to have, not required */
      }
      return next
    })
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-left"
          aria-expanded={open}
        >
          <span className="text-slate-400">{open ? '\u25be' : '\u25b8'}</span>
          <h2 className="text-lg font-semibold">
            Nieuw foundation-document maken{' '}
            <span className="text-sm font-normal text-slate-400">
              ({done.size}/{STEPS.length} stappen klaar)
            </span>
          </h2>
        </button>
        {done.size === STEPS.length && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">klaar</span>
        )}
      </div>
      {open && (
        <ol className="mt-3 space-y-2">
          {STEPS.map((step, i) => (
            <li key={step.title} className="flex gap-2.5">
              <button
                type="button"
                onClick={() => toggle(i)}
                title={done.has(i) ? 'Stap weer openen' : 'Stap afvinken'}
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border text-xs transition-colors ${
                  done.has(i)
                    ? 'border-emerald-500 bg-emerald-500 text-white'
                    : 'border-slate-300 bg-white text-transparent hover:border-slate-500'
                }`}
              >
                &#10003;
              </button>
              <div className={done.has(i) ? 'text-slate-400' : ''}>
                <p className={`text-sm font-medium ${done.has(i) ? 'line-through' : ''}`}>
                  {i + 1}. {step.title}
                </p>
                <p className="text-[13px] leading-snug text-slate-500">{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
