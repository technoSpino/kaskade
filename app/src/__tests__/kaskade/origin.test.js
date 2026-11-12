import { describe, expect, it } from 'vitest'
import { AI_BADGE, audioNote, cardBadge, originBadge, TTS_NOTE } from '../../lib/origin'

describe('originBadge', () => {
  it('labels AI-written content and shows the source of real material', () => {
    expect(originBadge('ai')).toEqual({ kind: 'ai', text: 'KI-geschrieben' })
    expect(originBadge('real', 'ARD Mediathek · NDR')).toEqual({ kind: 'real', text: 'ARD Mediathek · NDR' })
    expect(originBadge('real', null)).toBeNull() // real but nothing to name: no badge
    expect(originBadge(undefined)).toBeNull()
    expect(originBadge(undefined, null, 'ai')?.text).toBe(AI_BADGE) // Kaskade's own content
  })

  it('works for core-deck and mined cards', () => {
    expect(cardBadge({ n: 12, origin: 'ai', originSource: null }).kind).toBe('ai')
    expect(cardBadge({ n: 12 }).kind).toBe('ai')
    expect(cardBadge({ n: null, origin: 'real', originSource: 'Tatort: Schweigen' })).toEqual({ kind: 'real', text: 'Tatort: Schweigen' })
    expect(cardBadge({ n: null, origin: null })).toBeNull()
  })

  it('names the voice: clip snippet vs. computer voice', () => {
    expect(audioNote({ audio: 'mine-3.m4a' })).toBe('Originalton')
    expect(audioNote({ audio: null })).toBe(TTS_NOTE)
    expect(TTS_NOTE).toBe('Computerstimme')
  })
})
