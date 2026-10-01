import { useEffect, useState } from 'react'

/** What the user chose; "system" follows the operating system. The look itself is dark.css (data-theme="dark"). */
export type ThemePreference = 'system' | 'light' | 'dark'

const KEY = 'apollo.theme'
const QUERY = '(prefers-color-scheme: dark)'

export const THEME_LABELS: Record<ThemePreference, string> = {
  light: 'Licht',
  dark: 'Ambient (donker)',
  system: 'Automatisch',
}

export function storedTheme(): ThemePreference {
  try {
    const value = localStorage.getItem(KEY)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
    /* storage can be blocked (private window, embedded view): the default is fine */
  }
  return 'system'
}

export function resolveTheme(preference: ThemePreference): 'light' | 'dark' {
  if (preference === 'system') return window.matchMedia?.(QUERY).matches ? 'dark' : 'light'
  return preference
}

/** Put the theme on <html>. index.html does the same before the page paints, so there is no flash of the wrong one. */
export function applyTheme(preference: ThemePreference): void {
  document.documentElement.dataset.theme = resolveTheme(preference)
  document.documentElement.dataset.themePreference = preference
}

export function useTheme(): [ThemePreference, (next: ThemePreference) => void] {
  const [preference, setPreference] = useState<ThemePreference>(storedTheme)

  useEffect(() => {
    applyTheme(preference)
    if (preference !== 'system') return
    // "Automatisch" follows the system while the app is open
    const media = window.matchMedia(QUERY)
    const onChange = () => applyTheme('system')
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [preference])

  // another window (or the settings card and the top bar of this one) changed it
  useEffect(() => {
    const onStorage = (e: StorageEvent) => e.key === KEY && setPreference(storedTheme())
    const onLocal = () => setPreference(storedTheme())
    window.addEventListener('storage', onStorage)
    window.addEventListener('apollo-theme', onLocal)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener('apollo-theme', onLocal)
    }
  }, [])

  const choose = (next: ThemePreference) => {
    try {
      localStorage.setItem(KEY, next)
    } catch {
      /* not remembered, but it still applies now */
    }
    setPreference(next)
    window.dispatchEvent(new Event('apollo-theme'))
  }
  return [preference, choose]
}
