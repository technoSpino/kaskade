import { describe, expect, it } from 'vitest'
import { moveLines, weekLabel } from '../../lib/pauses'

describe('Woche frei nehmen (#36)', () => {
  it('names the week Mon–Sun', () => {
    expect(weekLabel({ from: '2026-10-19', to: '2026-10-25' })).toBe('Mo 19.10.–So 25.10.')
  })

  it('says what moves: the plan week, then each due date', () => {
    const preview = {
      week: { n: 3, theme: 'Alltag', was: '2026-11-02', now: '2026-11-09' },
      due: [{ id: 'kling-qualityland', title: 'Marc-Uwe Kling: QualityLand', was: '2026-11-07', now: '2026-11-14' }]
    }
    expect(moveLines(preview)).toEqual([
      'Woche 3 (Alltag) beginnt Mo 9.11. statt Mo 2.11. — alles danach eine Woche später.',
      'Marc-Uwe Kling: QualityLand: fällig Sa 14.11. statt Sa 7.11.'
    ])
    expect(moveLines({ ...preview, due: [] })).toHaveLength(1)
  })
})
