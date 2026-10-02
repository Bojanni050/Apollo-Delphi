import { useSyncExternalStore } from 'react'

/**
 * Whether Delphi Pulse is running, known app-wide: the menu item pulses while it does, also when you are on another page
 * (the run goes on in the backend; the request is awaited here, not in the page that started it).
 */
/** Sent when Delphi Pulse has accepted suggestions (documents got groups): the top bar looks again at what can be opened. */
export const GROUPS_CHANGED = 'apollo:groups-changed'

let running = 0
const listeners = new Set<() => void>()

const set = (delta: number) => {
  running += delta
  listeners.forEach((l) => l())
}

/** Runs `work` and counts it as a Pulse run for as long as it takes. */
export async function trackPulse<T>(work: () => Promise<T>): Promise<T> {
  set(1)
  try {
    return await work()
  } finally {
    set(-1)
  }
}

export function usePulseRunning(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => running > 0,
  )
}
