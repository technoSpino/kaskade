import { describe, expect, it } from 'vitest'
import { berlinMinutes, greeting, layoutBlocks, levelToPct, nextBlock, nowMarker, previewHint, shortDate, weekBars, weekStack } from '../../lib/heute'

const BLOCK = [
  { id: 'karten', start: '09:00', minutes: 30, kind: 'karten' },
  { id: 'input', start: '09:30', minutes: 55, kind: 'input' },
  { id: 'pause', start: '10:25', minutes: 10, kind: 'pause' },
  { id: 'lesen', start: '10:35', minutes: 30, kind: 'lesen' },
  { id: 'pruefung', start: '11:05', minutes: 25, kind: 'pruefung' }
]

describe('daily block', () => {
  it('lays out 09:00–11:30 = 150 minutes', () => {
    const l = layoutBlocks(BLOCK)
    expect(l.end - l.start).toBe(150)
    expect(l.items.reduce((s, b) => s + b.share, 0)).toBeCloseTo(1)
    expect(l.items[2].from).toBe(10 * 60 + 25)
  })

  it('places the now marker inside the block only', () => {
    expect(nowMarker(BLOCK, 9 * 60 + 20)).toBeCloseTo(13.33, 1)
    expect(nowMarker(BLOCK, 8 * 60)).toBeNull()
    expect(nowMarker(BLOCK, 12 * 60)).toBeNull()
  })

  it('suggests the running block, else the first open one, never the pause', () => {
    expect(nextBlock(BLOCK, [], 9 * 60 + 40).id).toBe('input')
    expect(nextBlock(BLOCK, ['input'], 9 * 60 + 40).id).toBe('karten')
    expect(nextBlock(BLOCK, ['karten'], 10 * 60 + 30).id).toBe('input')
    expect(nextBlock(BLOCK, ['karten', 'input', 'lesen', 'pruefung'], 600)).toBeNull()
  })
})

describe('levels and charts', () => {
  it('maps CEFR levels to bar positions', () => {
    expect(levelToPct('B1')).toBe(50)
    expect(levelToPct('A2+')).toBeGreaterThan(levelToPct('A2'))
    expect(levelToPct(null)).toBe(0)
  })

  it('scales weekly bars to at least 2.5 h', () => {
    expect(weekBars([0, 9000, 4500], 100)).toEqual([0, 100, 50])
    expect(weekBars([18000], 100)).toEqual([100])
  })

  it('stacks active and passive time on one scale', () => {
    expect(weekStack([4500, 0], [4500, 0], 100)).toEqual([{ aktiv: 50, passiv: 50 }, { aktiv: 0, passiv: 0 }])
    expect(weekStack([3600], [14400], 100)).toEqual([{ aktiv: 20, passiv: 80 }])
  })

  it('greets by time of day', () => {
    expect(greeting(9 * 60)).toBe('Guten Morgen')
    expect(greeting(15 * 60)).toBe('Hallo')
    expect(greeting(20 * 60)).toBe('Guten Abend')
  })

  it('reads Berlin time', () => {
    expect(berlinMinutes(new Date('2026-10-13T07:30:00Z'))).toBe(9 * 60 + 30)
    expect(berlinMinutes(new Date('2026-01-13T08:30:00Z'))).toBe(9 * 60 + 30) // winter time
  })
})

describe('preview days', () => {
  it('formats the plan start as a short German date', () => {
    expect(shortDate('2026-10-12')).toBe('Mo, 12. Oktober')
    expect(shortDate('2027-03-28')).toBe('So, 28. März')
  })

  it('explains why Start is disabled before the plan start and on weekends', () => {
    expect(previewHint({ day: null, beforeStart: true, weekend: true, planStart: '2026-10-12' }))
      .toBe('Dein Plan startet am Mo, 12. Oktober. Karten und Lesen gehen trotzdem über das Menü.')
    expect(previewHint({ day: null, beforeStart: false, weekend: true, planStart: '2026-10-12' }))
      .toMatch(/^Wochenende — der Lernblock läuft Mo–Fr\./)
  })

  it('has no hint on plan days', () => {
    expect(previewHint({ day: { focus: 'x' }, weekend: false })).toBeNull()
    expect(previewHint(null)).toBeNull()
  })
})
