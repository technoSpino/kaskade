import { describe, expect, it } from 'vitest'
import { defaultView, groupTokens, markGlossary, paragraphs, storedView, storeView, viewFlags } from '../../lib/reader'

const G = [
  { term: 'Heizung', gloss: 'heating' },
  { term: 'Heizungsrohr', gloss: 'heating pipe' },
  { term: 'Miete', gloss: 'rent' }
]

describe('markGlossary', () => {
  it('marks whole-word glossary terms and keeps the text intact', () => {
    const p = 'Die Heizung ist kalt, und die Miete ist hoch.'
    const segs = markGlossary(p, G)
    expect(segs.map((s) => s.text).join('')).toBe(p)
    expect(segs.filter((s) => s.entry).map((s) => s.text)).toEqual(['Heizung', 'Miete'])
  })

  it('prefers the longest term and ignores parts of other words', () => {
    const segs = markGlossary('Das Heizungsrohr ist alt. Mieter zahlen.', G)
    expect(segs.filter((s) => s.entry).map((s) => s.entry.gloss)).toEqual(['heating pipe'])
  })

  it('marks every occurrence', () => {
    expect(markGlossary('Miete, Miete, Miete!', G).filter((s) => s.entry)).toHaveLength(3)
  })

  it('handles an empty glossary', () => {
    expect(markGlossary('Hallo.', [])).toEqual([{ text: 'Hallo.' }])
  })
})

describe('paragraphs', () => {
  it('splits on blank lines', () => {
    expect(paragraphs('Eins.\n\nZwei.\n \nDrei.')).toEqual(['Eins.', 'Zwei.', 'Drei.'])
  })
})

describe('token joiner (no line break inside a word + its punctuation)', () => {
  // spaCy tokens for: Die Heizung ist kalt. „Nicht schon wieder!“, denkt Frau Kaya. Sie sagt: ‚Na gut‘ (leise).
  const raw = [['Die', ' '], ['Heizung', ' '], ['ist', ' '], ['kalt', ''], ['.', ' '], ['„', ''], ['Nicht', ' '], ['schon', ' '],
    ['wieder', ''], ['!', ''], ['“', ''], [',', ' '], ['denkt', ' '], ['Frau', ' '], ['Kaya', ''], ['.', ' '], ['Sie', ' '],
    ['sagt', ''], [':', ' '], ['‚', ''], ['Na', ' '], ['gut', ''], ['‘', ' '], ['(', ''], ['leise', ''], [')', ''], ['.', '']]
  const tokens = raw.map(([text, ws], i) => ({ i, text, ws }))
  const joined = groupTokens(tokens).map((g) => g.map((t) => t.text).join(''))

  it('glues opening quotes to the next word and closing marks to the previous one', () => {
    expect(joined).toContain('„Nicht')
    expect(joined).toContain('wieder!“,')
    expect(joined).toContain('‚Na')
    expect(joined).toContain('gut‘')
    expect(joined).toContain('(leise).')
    expect(joined).toContain('kalt.')
    expect(joined).toContain('Kaya.')
  })

  it('keeps every token exactly once, in order', () => {
    expect(groupTokens(tokens).flat().map((t) => t.i)).toEqual(tokens.map((t) => t.i))
    expect(groupTokens([])).toEqual([])
  })
})

describe('reader view toggle', () => {
  it('defaults to new words only in phase 2B, both otherwise; a stored choice wins', () => {
    expect(defaultView(null, '2B')).toBe('neu')
    expect(defaultView(null, '2A')).toBe('beides')
    expect(defaultView(null, null)).toBe('beides')
    expect(defaultView('kasus', '2B')).toBe('kasus')
    expect(defaultView('quatsch', '2B')).toBe('neu')
  })

  it('maps views to word states and case lens', () => {
    expect(viewFlags('neu')).toEqual({ states: true, lens: false })
    expect(viewFlags('kasus')).toEqual({ states: false, lens: true })
    expect(viewFlags('beides')).toEqual({ states: true, lens: true })
  })

  it('remembers the choice and survives blocked storage', () => {
    const mem = new Map()
    const storage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) }
    storeView('kasus', storage)
    expect(storedView(storage)).toBe('kasus')
    const blocked = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }
    expect(() => storeView('neu', blocked)).not.toThrow()
    expect(storedView(blocked)).toBeNull()
  })
})
