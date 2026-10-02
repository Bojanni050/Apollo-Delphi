import { createContext, useContext } from 'react'

/** The two languages of the interface. Dutch is the default; English is the alternative. */
export type Lang = 'nl' | 'en'

const STORAGE_KEY = 'apollo.lang'

export function loadLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'en' ? 'en' : 'nl'
}

export function saveLang(lang: Lang) {
  localStorage.setItem(STORAGE_KEY, lang)
}

/** Every interface string that differs between Dutch and English, per language. */
const DICT: Record<Exclude<string, '_'>, { nl: string; en: string }> = {
  'status.gelezen': { nl: 'gelezen', en: 'read' },
  'status.pending': { nl: 'in wachtrij', en: 'pending' },
  'status.processing': { nl: 'bezig', en: 'processing' },
  'status.indexed': { nl: 'geïndexeerd', en: 'indexed' },
  'status.failed': { nl: 'mislukt', en: 'failed' },
  'status.error': { nl: 'fout', en: 'error' },
  'status.parsed': { nl: 'gelezen', en: 'parsed' },
  'status.resolved': { nl: 'opgelost', en: 'resolved' },
  'status.completed': { nl: 'afgerond', en: 'completed' },
  'status.confirmed': { nl: 'bevestigd', en: 'confirmed' },
  'status.disputed': { nl: 'betwist', en: 'disputed' },
  'status.remaining_contradiction': { nl: 'tegenstrijdig', en: 'contradictory' },
  'status.open': { nl: 'open', en: 'open' },
  'status.accepted': { nl: 'geaccepteerd', en: 'accepted' },
  'status.rejected': { nl: 'afgewezen', en: 'rejected' },
  'status.unresolved': { nl: 'onopgelost', en: 'unresolved' },
  'status.generating': { nl: 'bezig met genereren', en: 'generating' },
  'status.verified': { nl: 'gecontroleerd', en: 'verified' },
  'status.unverified': { nl: 'niet gecontroleerd', en: 'unverified' },
  'status.warning': { nl: 'waarschuwing', en: 'warning' },
  'status.info': { nl: 'info', en: 'info' },

  'issues.title': { nl: 'Issues', en: 'Issues' },
  'issues.empty': { nl: 'Nog geen issues. Draai eerst een analyse.', en: 'No issues yet. Run an analysis first.' },
  'issues.select': { nl: 'Kies een issue om het te bekijken.', en: 'Select an issue to inspect it.' },
  'issues.investigate': { nl: 'Onderzoeken', en: 'Investigate' },
  'issues.investigating': { nl: 'Onderzoeken…', en: 'Investigating…' },
  'issues.conflictingClaims': { nl: 'Conflicterende claims', en: 'Conflicting claims' },
  'issues.noClaims': { nl: 'Geen gekoppelde claims.', en: 'No linked claims.' },
  'issues.evidence': { nl: 'Bewijs', en: 'Evidence' },
  'issues.noEvidence': { nl: 'Geen gekoppeld bewijs.', en: 'No linked evidence.' },
  'issues.resolution': { nl: 'Voorgestelde oplossing', en: 'Proposed resolution' },
  'issues.conclusion': { nl: 'Conclusie', en: 'Conclusion' },
  'issues.reasoning': { nl: 'Redenering', en: 'Reasoning' },
  'issues.status': { nl: 'Status', en: 'Status' },
  'issues.confidence': { nl: 'zekerheid', en: 'confidence' },
  'issues.unresolvedUncertainty': { nl: 'Resterende onzekerheid', en: 'Unresolved uncertainty' },
  'issues.note': { nl: 'Optionele notitie / aanvullende informatie', en: 'Optional note / additional information' },
  'issues.accept': { nl: 'Accepteren', en: 'Accept' },
  'issues.reject': { nl: 'Afwijzen', en: 'Reject' },
  'issues.markUnresolved': { nl: 'Onopgelost laten', en: 'Mark unresolved' },
  'issues.document': { nl: 'document', en: 'document' },
  'issues.value': { nl: 'waarde', en: 'value' },
  'issues.page': { nl: 'pagina', en: 'page' },

  'knowledge.facts': { nl: 'Feiten', en: 'Facts' },
  'knowledge.derived': { nl: 'Afgeleide conclusies', en: 'Derived conclusions' },
  'knowledge.assumptions': { nl: 'Aannames', en: 'Assumptions' },
  'knowledge.decisions': { nl: 'Beslissingen', en: 'Decisions' },
  'knowledge.unresolvedQuestions': { nl: 'Onopgeloste vragen', en: 'Unresolved questions' },
  'knowledge.resolvedContradictions': { nl: 'Opgeloste tegenstrijdigheden', en: 'Resolved contradictions' },
  'knowledge.remainingContradictions': { nl: 'Resterende tegenstrijdigheden', en: 'Remaining contradictions' },

  'analysis.collection': { nl: 'Verzamelde analyse', en: 'Collection analysis' },
  'analysis.run': { nl: 'Analyse draaien', en: 'Run analysis' },
  'analysis.running': { nl: 'Bezig…', en: 'Running…' },
  'analysis.noClaims': { nl: 'Nog geen claims uitgelezen.', en: 'No claims extracted yet.' },
  'analysis.openQuestions': { nl: 'open vragen', en: 'open questions' },
  'analysis.contradictions': { nl: 'tegenstrijdigheden', en: 'contradictions' },

  'generated.title': { nl: 'Genereren', en: 'Generate' },
  'generated.reportTitle': { nl: 'Titel van het rapport', en: 'Report title' },
  'generated.generate': { nl: 'Genereren uit kennis', en: 'Generate from knowledge state' },
  'generated.generating': { nl: 'Genereren…', en: 'Generating…' },
  'generated.history': { nl: 'Geschiedenis', en: 'History' },
  'generated.verificationFindings': { nl: 'Controlebevindingen', en: 'Verification findings' },

  'documents.upload': { nl: 'Documenten uploaden', en: 'Upload documents' },
  'documents.name': { nl: 'Naam', en: 'Name' },
  'documents.type': { nl: 'Type', en: 'Type' },
  'documents.size': { nl: 'Grootte', en: 'Size' },
  'documents.status': { nl: 'Status', en: 'Status' },
  'documents.uploaded': { nl: 'Toegevoegd', en: 'Uploaded' },

  'appearance.language': { nl: 'Taal', en: 'Language' },
  'appearance.languageHint': {
    nl: 'Nederlands is de standaardtaal van Apollo. Kies Engels als je dat liever hebt; de interface herlaadt meteen.',
    en: 'Dutch is the default language of Apollo. Choose English if you prefer it; the interface reloads at once.',
  },
}

export type DictKey = keyof typeof DICT

/** Whether the dictionary has a key (so callers can fall back to the raw value). */
export function hasKey(key: string): key is DictKey {
  return key in DICT
}

export const LangContext = createContext<Lang>('nl')

/** The translation function the whole interface uses; Dutch where a key is missing. */
export function translate(lang: Lang, key: DictKey): string {
  return DICT[key]?.[lang] ?? DICT[key]?.nl ?? key
}

export function useLang() {
  return useContext(LangContext)
}

/** `useT()` gives every component one `t(key)` in the active language. */
export function useT() {
  const lang = useContext(LangContext)
  return (key: DictKey) => translate(lang, key)
}
