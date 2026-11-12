import { describe, expect, it } from 'vitest'
import { applyTheme, resolveTheme, storeTheme, storedTheme, systemTheme, THEMES } from '../../lib/theme'

const memory = () => {
  const m = new Map()
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) }
}
const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }

describe('theme', () => {
  it('has six themes with German labels', () => {
    expect(THEMES.map((t) => t.label)).toEqual(['Signal', 'Nacht', 'Papier', 'Bauhaus', 'Fokus', 'Magazin'])
  })

  it('stores and reads the choice', () => {
    const s = memory()
    storeTheme('papier', s)
    expect(storedTheme(s)).toBe('papier')
  })

  it('ignores unknown values and broken storage', () => {
    const s = memory()
    s.setItem('kaskade-theme', 'neon')
    expect(storedTheme(s)).toBeNull()
    expect(storedTheme(broken)).toBeNull()
    expect(() => storeTheme('nacht', broken)).not.toThrow()
  })

  it('follows prefers-color-scheme without a choice', () => {
    expect(systemTheme(() => ({ matches: true }))).toBe('nacht')
    expect(systemTheme(() => ({ matches: false }))).toBe('signal')
    expect(systemTheme(undefined)).toBe('signal')
  })

  it('resolves local > server > system', () => {
    expect(resolveTheme({ local: 'fokus', server: 'papier', system: 'nacht' })).toBe('fokus')
    expect(resolveTheme({ local: null, server: 'papier', system: 'nacht' })).toBe('papier')
    expect(resolveTheme({ local: null, server: 'xx', system: 'nacht' })).toBe('nacht')
  })

  it('sets data-theme only for known themes', () => {
    const attrs = {}
    const root = { setAttribute: (k, v) => { attrs[k] = v } }
    applyTheme('bauhaus', root)
    applyTheme('neon', root)
    expect(attrs['data-theme']).toBe('bauhaus')
  })
})
