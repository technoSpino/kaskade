import { describe, expect, it } from 'vitest'
import { CAP_MS, clockText, createRevealTimer, finalTime, grade, progress, runningTime, storeAutoplay, storedAutoplay, waitLine } from '../../lib/reveal'

function clock() {
  let t = 0
  const now = () => t
  now.add = (ms) => { t += ms }
  return now
}

describe('reveal timer (#25)', () => {
  it('measures from showing the card to revealing it', () => {
    const now = clock()
    const timer = createRevealTimer(now)
    timer.start()
    now.add(2300)
    expect(timer.stop()).toBe(2300)
  })
  it('pauses while the tab is hidden or the window has lost focus', () => {
    const now = clock()
    const timer = createRevealTimer(now)
    timer.start()
    now.add(1000)
    timer.pause() // hidden
    now.add(30_000)
    timer.resume() // visible again
    now.add(500)
    timer.pause(); timer.pause() // blur twice: counted once
    now.add(5000)
    timer.resume(); timer.resume()
    now.add(500)
    expect(timer.stop()).toBe(2000)
  })
  it('is capped at 60 s', () => {
    const now = clock()
    const timer = createRevealTimer(now)
    timer.start()
    now.add(95_000)
    expect(timer.ms).toBe(CAP_MS)
    expect(timer.stop()).toBe(60_000)
  })
  it('starts from zero for the next card', () => {
    const now = clock()
    const timer = createRevealTimer(now)
    timer.start(); now.add(4000); timer.stop()
    timer.start(); now.add(700)
    expect(timer.stop()).toBe(700)
  })
})

describe('grade from the time', () => {
  // 3 words: typical 2.85 s → Leicht ≤ 1995 ms, Gut ≤ 4560 ms; 10 words: 6 s → 4200 / 9600
  const short = { easyMs: 1995, hardMs: 4560 }
  const long = { easyMs: 4200, hardMs: 9600 }
  it('Leicht / Gut / Schwer by sentence length', () => {
    expect(grade(2000 - 5, short)).toBe(4)
    expect(grade(3000, short)).toBe(3)
    expect(grade(4561, short)).toBe(2)
    expect(grade(3000, long)).toBe(4)  // the same 3 s is quick for a long sentence
    expect(grade(9000, long)).toBe(3)
    expect(grade(20_000, long)).toBe(2)
    expect(grade(1000, null)).toBe(3)
  })
})

describe('progress and the waiting line', () => {
  it('cards done against cards open, never 100 % while one is open', () => {
    expect(progress({ doneToday: 12, left: 18 })).toEqual({ done: 12, left: 18, pct: 40, text: '12 fertig · 18 offen' })
    expect(progress({ doneToday: 29, left: 1 }).pct).toBe(97)
    expect(progress({ doneToday: 30, left: 0 }).pct).toBe(100)
    expect(progress(null).text).toBe('0 fertig · 0 offen')
  })
  it('counts down to when the waiting cards come back', () => {
    const at = '2026-10-14T07:06:00Z'
    const t = Date.parse('2026-10-14T07:00:00Z')
    expect(waitLine({ cards: 3, at }, t)).toBe('Noch 3 Karten — kommen in 6 Min wieder')
    expect(waitLine({ cards: 1, at }, t + 5 * 60_000 + 15_000)).toBe('Noch 1 Karte — kommt in 45 s wieder')
    expect(waitLine(null, t)).toBeNull()
  })
})

describe('the timer on the card (#28)', () => {
  const timing = { easyMs: 1995, hardMs: 4560 }
  it('0:07 while it runs, 7,3 s once revealed, 60 s+ at the cap', () => {
    expect(runningTime(0)).toBe('0:00')
    expect(runningTime(7300)).toBe('0:07')
    expect(runningTime(59_999)).toBe('0:59')
    expect(runningTime(60_000)).toBe('60 s+')
    expect(finalTime(7300)).toBe('7,3 s')
    expect(finalTime(7399)).toBe('7,3 s') // never more than it showed
    expect(finalTime(0)).toBe('0,0 s')
    expect(finalTime(59_999)).toBe('59,9 s')
    expect(finalTime(60_000)).toBe('60 s+')
  })
  it('next to the time: what "Gewusst" means right now', () => {
    expect(clockText(0, 'run', timing)).toBe('0:00 · Leicht')
    expect(clockText(1995, 'run', timing)).toBe('0:01 · Leicht')
    expect(clockText(1996, 'run', timing)).toBe('0:01 · Gut')
    expect(clockText(4560, 'run', timing)).toBe('0:04 · Gut')
    expect(clockText(4561, 'run', timing)).toBe('0:04 · Schwer')
    expect(clockText(60_000, 'run', timing)).toBe('60 s+ · Schwer')
    expect(clockText(7300, 'done', timing)).toBe('7,3 s · Schwer')
    expect(clockText(3000, 'done', timing)).toBe('3,0 s · Gut')
  })
  it('"0:00 · Audio" during the clip, "pausiert" without focus', () => {
    expect(clockText(4000, 'audio', timing)).toBe('0:00 · Audio')
    expect(clockText(7300, 'pause', timing)).toBe('0:07 · pausiert')
  })
  it('reset: back to 0:00 and not running while the audio plays; revealing then is 0 ms', () => {
    const now = clock()
    const timer = createRevealTimer(now)
    timer.start(); now.add(5000); timer.stop()
    timer.reset()
    now.add(4000) // the clip
    expect([timer.ms, timer.running]).toEqual([0, false])
    expect(timer.stop()).toBe(0)
    timer.reset(); now.add(4000)
    timer.start(); now.add(1500)
    expect(timer.stop()).toBe(1500)
  })
})

describe('"Audio automatisch abspielen" is remembered (#28)', () => {
  const mem = (v = {}) => ({ getItem: (k) => v[k] ?? null, setItem: (k, x) => { v[k] = x }, v })
  it('on by default, off once he unticks it', () => {
    const s = mem()
    expect(storedAutoplay(s)).toBe(true)
    storeAutoplay(false, s)
    expect(s.v).toEqual({ 'kaskade.karten.autoplay': '0' })
    expect(storedAutoplay(s)).toBe(false)
    storeAutoplay(true, s)
    expect(storedAutoplay(s)).toBe(true)
  })
  it('blocked or missing storage: on, and no error', () => {
    const broken = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
    expect(storedAutoplay(broken)).toBe(true)
    expect(() => storeAutoplay(false, broken)).not.toThrow()
    expect(storedAutoplay(undefined)).toBe(true)
  })
})
