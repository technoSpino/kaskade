import { describe, expect, it } from 'vitest'
import { splitTarget, cardWords, markTargets } from '../../lib/cards'

describe('splitTarget', () => {
  it('splits around the first occurrence', () => {
    expect(splitTarget('Ich habe heute keine Zeit.', 'Zeit')).toEqual({ pre: 'Ich habe heute keine ', target: 'Zeit', post: '.' })
  })

  it('keeps the whole sentence when the target is missing', () => {
    expect(splitTarget('Hallo!', 'Tschüss')).toEqual({ pre: 'Hallo!', target: '', post: '' })
  })

  it('highlights only the first occurrence', () => {
    const p = splitTarget('Das ist das Haus.', 'das')
    expect(p.pre).toBe('Das ist ')
    expect(p.post).toBe(' Haus.')
  })
})

describe('mined cards with more than one word (#19)', () => {
  const S = 'Wenn man überhetzt, versaust du dir nachher die Chance.'

  it('marks every target word in the sentence', () => {
    expect(markTargets(S, ['versaust', 'überhetzt'])).toEqual([
      { text: 'Wenn man ', mark: false },
      { text: 'überhetzt', mark: true },
      { text: ', ', mark: false },
      { text: 'versaust', mark: true },
      { text: ' du dir nachher die Chance.', mark: false }
    ])
    expect(markTargets(S, ['fehlt'])).toEqual([{ text: S, mark: false }])
    expect(markTargets('Chance', ['Chance', 'Chance'])).toEqual([{ text: 'Chance', mark: true }])
  })

  it('lists the card word first, then the added ones, with their KI marks', () => {
    const card = { target: 'überhetzt', lemma: 'überhetzen', display: 'überhetzen', gloss: 'to rush', case: null, note: null, aiFields: ['gloss'],
      words: [{ target: 'versaust', lemma: 'versauen', display: 'versauen', gloss: 'to mess up', case: null, note: null, ai: ['lemma'] }] }
    expect(cardWords(card).map((w) => [w.target, w.ai])).toEqual([['überhetzt', ['gloss']], ['versaust', ['lemma']]])
    expect(cardWords({ ...card, aiFields: undefined, words: undefined })).toHaveLength(1)
  })
})
