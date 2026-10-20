import { describe, expect, it } from 'vitest'
import { answerIds, isComplete, timeLeft, verdictLabel } from '../../lib/practice'

describe('practice helpers', () => {
  const rf = { questions: [{ id: 'a' }, { id: 'b' }] }
  const zu = { situations: [{ id: 's1' }] }

  it('knows which answers an item needs', () => {
    expect(answerIds(rf)).toEqual(['a', 'b'])
    expect(answerIds(zu)).toEqual(['s1'])
  })

  it('treats false and 0 as given answers', () => {
    expect(isComplete(rf, { a: false, b: 0 })).toBe(true)
    expect(isComplete(rf, { a: true })).toBe(false)
    expect(isComplete(zu, { s1: '0' })).toBe(true)
  })

  it('counts down and stops at zero', () => {
    expect(timeLeft(10, 0, 60_000)).toBe(540)
    expect(timeLeft(1, 0, 120_000)).toBe(0)
  })

  it('labels results against the 60 % pass mark', () => {
    expect(verdictLabel(0.6)).toContain('bestanden')
    expect(verdictLabel(0.59)).toContain('unter')
    expect(verdictLabel(null)).toBe('noch nicht geübt')
  })
})
