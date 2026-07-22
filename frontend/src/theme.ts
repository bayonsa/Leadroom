export type ThemeId = 'brushstroke' | 'genesis' | 'flip7' | 'rawblock' | 'evreghen' | 'ember' | 'insightdeck' | 'vercel' | 'trustblue' | 'zengrid'

export const DEFAULT_THEME: ThemeId = 'brushstroke'
export const THEME_STORAGE_KEY = 'leadroom-theme'

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { finished: Promise<void> }
}

const THEME_IDS = new Set<ThemeId>(['brushstroke', 'genesis', 'flip7', 'rawblock', 'evreghen', 'ember', 'insightdeck', 'vercel', 'trustblue', 'zengrid'])

export function isThemeId(value: unknown): value is ThemeId {
  return typeof value === 'string' && THEME_IDS.has(value as ThemeId)
}

function commitTheme(theme: ThemeId) {
  document.documentElement.dataset.theme = theme
  window.localStorage.setItem(THEME_STORAGE_KEY, theme)
}

export function applyTheme(theme: ThemeId, animate = true) {
  if (document.documentElement.dataset.theme === theme) {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    return
  }

  const viewDocument = document as ViewTransitionDocument
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!animate || reduceMotion || !viewDocument.startViewTransition) {
    commitTheme(theme)
    return
  }

  document.documentElement.classList.add('theme-transitioning')
  const transition = viewDocument.startViewTransition(() => commitTheme(theme))
  void transition.finished.finally(() => document.documentElement.classList.remove('theme-transitioning'))
}

export function initializeTheme() {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  applyTheme(isThemeId(stored) ? stored : DEFAULT_THEME, false)
}
