// Theme switching ("Stil"). The choice lives in localStorage (fast, per browser)
// and in server settings (so it survives a new browser). Without a choice the
// theme follows prefers-color-scheme: Signal (light) or Nacht (dark).

export const THEMES = [
  { id: 'signal', label: 'Signal' },
  { id: 'nacht', label: 'Nacht' },
  { id: 'papier', label: 'Papier' },
  { id: 'bauhaus', label: 'Bauhaus' },
  { id: 'fokus', label: 'Fokus' },
  { id: 'magazin', label: 'Magazin' }
]

const KEY = 'kaskade-theme'
const ids = new Set(THEMES.map((t) => t.id))

export const isTheme = (id) => ids.has(id)

export function storedTheme(storage = globalThis.localStorage) {
  try {
    const v = storage?.getItem(KEY)
    return isTheme(v) ? v : null
  } catch {
    return null
  }
}

export function storeTheme(id, storage = globalThis.localStorage) {
  try {
    storage?.setItem(KEY, id)
  } catch {
    // private mode / blocked storage: the server setting still remembers it
  }
}

export function systemTheme(matchMedia = globalThis.matchMedia) {
  try {
    return matchMedia?.('(prefers-color-scheme: dark)').matches ? 'nacht' : 'signal'
  } catch {
    return 'signal'
  }
}

/** Local choice wins, then the server's, then the system preference. */
export function resolveTheme({ local, server, system }) {
  if (isTheme(local)) return local
  if (isTheme(server)) return server
  return system
}

export function applyTheme(id, root = globalThis.document?.documentElement) {
  if (root && isTheme(id)) root.setAttribute('data-theme', id)
}
