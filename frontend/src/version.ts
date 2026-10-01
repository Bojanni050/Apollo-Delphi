/**
 * Build number under the title in the sidebar: "0." + date and time of the build, made by vite.config.ts.
 * It changes by itself with every build (npm run build, the desktop app's start, the dev server); nothing to update.
 */
declare const __BUILD_VERSION__: string
declare const __BUILD_TIME__: string

export const BUILD_VERSION: string = __BUILD_VERSION__
/** The same moment as a readable day and time, e.g. "do 1 okt 2026 · 15:50". */
export const BUILD_TIME: string = __BUILD_TIME__
