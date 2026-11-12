import { describe, expect, it } from 'vitest'
import { clipStatus, clock, endsSentence, formatTime, jobLabel, inside, isNonSpeech, JUMP, jumpedBack, LEAD, lineAt, pausedBefore, pickTrack, rangeStart, resumeAt, seekTarget, sentenceAround, shouldPause, shownLine, speechCues, stepLine, storeTrack, storedTrack } from '../../lib/watch'

const CUES = [
  { start: 1, end: 2.5, text: 'Wo waren Sie gestern Abend?' },
  { start: 3, end: 4, text: 'Zu Hause.' },
  { start: 6, end: 8, text: 'Das glaube ich Ihnen nicht.' }
]

describe('non-speech cues', () => {
  it('skips music and sound cues like the server', () => {
    expect(isNonSpeech('♪ La la la ♪')).toBe(true)
    expect(isNonSpeech('* Stimmen und Lachen *')).toBe(true)
    expect(isNonSpeech('[Klopfen]')).toBe(true)
    expect(isNonSpeech('(dumpf)')).toBe(true)
    expect(isNonSpeech('(leise) Komm her.')).toBe(false)
    expect(isNonSpeech('Na?')).toBe(false)
    expect(speechCues([...CUES, { start: 9, end: 10, text: '(schreit)' }])).toHaveLength(3)
  })

  it('#30: a spoken line that is only "Musik" is Whisper hearing the theme tune, not speech', () => {
    for (const t of ['Musik', 'Musik.', ' musik ']) expect(isNonSpeech(t)).toBe(true)
    for (const t of ['Musik!', 'Musik ist laut.']) expect(isNonSpeech(t)).toBe(false)
  })
})

describe('cue navigation', () => {
  it('finds the line at a time (the last one that started)', () => {
    expect(lineAt(CUES, 0.5)).toBe(-1)
    expect(lineAt(CUES, 1)).toBe(0)
    expect(lineAt(CUES, 2.7)).toBe(0) // between lines: still the last line
    expect(lineAt(CUES, 3.5)).toBe(1)
    expect(lineAt(CUES, 100)).toBe(2)
    expect(inside(CUES, 0, 2.7)).toBe(false)
    expect(inside(CUES, 1, 3.5)).toBe(true)
  })

  it('steps to the previous and next line from the shown line, clamped', () => {
    expect(stepLine(CUES, 1, 1)).toBe(2)
    expect(stepLine(CUES, 1, -1)).toBe(0)
    expect(stepLine(CUES, 0, -1)).toBe(0)
    expect(stepLine(CUES, -1, 1)).toBe(0) // before the first line → the first line
    expect(stepLine(CUES, 2, 1)).toBe(2)
    expect(stepLine([], 0, 1)).toBe(-1)
  })

  it('auto-pauses once at the end of each line', () => {
    expect(shouldPause(CUES, 2.0, null)).toBe(-1) // still speaking
    expect(shouldPause(CUES, 2.6, null)).toBe(0) // line 0 over → pause
    expect(shouldPause(CUES, 2.7, 0)).toBe(-1) // already paused for line 0 → play on
    expect(shouldPause(CUES, 4.1, 0)).toBe(1)
  })
})

describe('tight line changes (#18)', () => {
  // Tatort: Schweigen — 29 % of line changes have a 0.12 s gap; some lines are back to back.
  const TIGHT = [
    { start: 140.0, end: 143.56, text: 'Was haben Sie da gesehen?' },
    { start: 143.68, end: 146.0, text: 'Nichts. Ich war gar nicht da.' },
    { start: 146.0, end: 148.5, text: 'Das glaube ich Ihnen nicht.' },
    { start: 150.0, end: 152.0, text: 'Gehen Sie.' }
  ]

  it('never shows the next line before the current one has ended', () => {
    expect(shownLine(TIGHT, 143.45)).toBe(0) // 0.15 s lead would reach 143.60 > 143.56 … still line 0
    expect(shownLine(TIGHT, 143.55)).toBe(0)
    expect(shownLine(TIGHT, 143.56)).toBe(1) // line 0 over, inside the 0.12 s gap: next line may show
    expect(shownLine(TIGHT, 145.99)).toBe(1) // gap 0: line 1 until its very end
    expect(shownLine(TIGHT, 146.0)).toBe(2)
    expect(shownLine(TIGHT, 149.0)).toBe(2) // real gap: the last line stays …
    expect(shownLine(TIGHT, 149.86)).toBe(3) // … the next appears at most LEAD early
    expect(shownLine(TIGHT, 149.8)).toBe(2)
    expect(LEAD).toBe(0.15)
  })

  it('keeps the line auto-pause stopped after, wherever the playhead overshot to', () => {
    expect(shownLine(TIGHT, 143.6, 0)).toBe(0) // paused in the 0.12 s gap
    expect(shownLine(TIGHT, 146.03, 1)).toBe(1) // paused a frame into the back-to-back line
    expect(shownLine(TIGHT, 146.03, -1)).toBe(2) // played on: the new line
  })

  it('pauses for the line just heard, also with gap 0.12 s and gap 0', () => {
    expect(shouldPause(TIGHT, 143.5, null, 143.48)).toBe(-1)
    expect(shouldPause(TIGHT, 143.58, null, 143.54)).toBe(0) // in the gap
    expect(shouldPause(TIGHT, 143.70, null, 143.54)).toBe(0) // tick overshot into line 1
    expect(shouldPause(TIGHT, 143.70, 0, 143.54)).toBe(-1) // once
    expect(shouldPause(TIGHT, 146.02, 0, 145.99)).toBe(1) // back to back: line 1 just ended
    expect(shouldPause(TIGHT, 146.02, 1, 145.99)).toBe(-1)
    expect(shouldPause(TIGHT, 146.5, 0, 140.0)).toBe(-1) // a jump, not playback: no pause for line 1
  })

  it('← / → / R from the held line, and seeking never lands in the previous line', () => {
    expect(stepLine(TIGHT, shownLine(TIGHT, 146.03, 1), 1)).toBe(2) // not 3: line 2 is still unheard
    expect(seekTarget(TIGHT, 0)).toBeCloseTo(139.9)
    expect(seekTarget(TIGHT, 1)).toBeCloseTo(143.58) // 0.1 s lead-in fits in the gap
    expect(seekTarget(TIGHT, 2)).toBe(146.0) // back to back: start exactly at the line
    expect(shownLine(TIGHT, seekTarget(TIGHT, 2))).toBe(2)
    expect(shownLine(TIGHT, seekTarget(TIGHT, 1))).toBe(1)
  })

  it('resumes at the saved position unless it is at the very end', () => {
    expect(resumeAt(754.2, 5360)).toBe(754.2)
    expect(resumeAt(1, 5360)).toBe(0)
    expect(resumeAt(5358, 5360)).toBe(0)
  })

  it('formats clip times', () => {
    expect(formatTime(754)).toBe('12:34')
    expect(formatTime(5361)).toBe('1:29:21')
    expect(formatTime(0)).toBe('0:00')
  })
})

describe('clip conversion status', () => {
  it('explains converting and failed clips, nothing for ready ones', () => {
    expect(clipStatus({ status: 'converting' })).toMatch(/umgewandelt/)
    expect(clipStatus({ status: 'original' })).toMatch(/Originaldatei/)
    expect(clipStatus({ status: 'ready' })).toBe('')
  })
})

describe('Mediathek job progress', () => {
  const MB = 1024 * 1024
  it('describes each phase in German', () => {
    expect(jobLabel({ status: 'running', phase: 'start', downloaded: 0 })).toBe('Verbinde mit der Mediathek …')
    expect(jobLabel({ status: 'running', phase: 'download', downloaded: 38 * MB, total: 145 * MB, speed: 7.9 * MB })).toBe('38 von 145 MB · 7,9 MB/s')
    expect(jobLabel({ status: 'running', phase: 'download', downloaded: 2.5 * MB, total: null })).toBe('2,5 MB')
    expect(jobLabel({ status: 'running', phase: 'convert', downloaded: 1 })).toMatch(/vorbereitet/)
    expect(jobLabel({ status: 'error', message: 'Geo-Sperre' })).toBe('Geo-Sperre')
    expect(jobLabel({ status: 'done' })).toBe('Fertig.')
  })
})

describe('plan ranges (#16)', () => {
  it('formats range times as minutes past an hour', () => {
    expect(clock(1814)).toBe('30:14')
    expect(clock(5361)).toBe('89:21')
    expect(clock(0)).toBe('0:00')
  })

  it('starts at the range, resumes inside it, catches up when behind', () => {
    expect(rangeStart(1814, 3640, 1812)).toMatchObject({ at: 1814, reached: false, note: 'Heute: 30:14–60:40.' })
    expect(rangeStart(1814, 3640, 0)).toMatchObject({ at: 1814 })
    expect(rangeStart(1814, 3640, 1200)).toMatchObject({ at: 1200, note: 'Ab deiner Position (20:00) bis 60:40.' })
    expect(rangeStart(1814, 3640, 2400)).toMatchObject({ at: 2400, note: 'Weiter ab 40:00 bis 60:40.' })
    expect(rangeStart(0, 1814, 1812)).toMatchObject({ reached: true })
    expect(rangeStart(2, 4, 0)).toMatchObject({ at: 2, reached: false }) // a short range: not "reached" before it starts
  })

  it('#30: a position that went backwards after the previous range was reached does not pull him back', () => {
    // Thursday: yesterday's part was reached at 62:26, then a jump saved 0:06
    expect(rangeStart(3746, 5361, 6.85, 3746)).toEqual({ at: 3746, reached: false, note: 'Heute: 62:26–89:21 (zuletzt gespeichert: 0:06).' })
    expect(rangeStart(3746, 5361, 6.85, 3750.2)).toMatchObject({ at: 3746 })
    // really behind: he stopped before yesterday's end → from his position, as before
    expect(rangeStart(3746, 5361, 3100, 3100)).toMatchObject({ at: 3100, note: 'Ab deiner Position (51:40) bis 89:21.' })
    expect(rangeStart(3746, 5361, 3100, null)).toMatchObject({ at: 3100 })
    expect(rangeStart(3746, 5361, 3100)).toMatchObject({ at: 3100 })
    // inside or past the range: unchanged
    expect(rangeStart(3746, 5361, 3800, 3746)).toMatchObject({ at: 3800, note: 'Weiter ab 63:20 bis 89:21.' })
    expect(rangeStart(3746, 5361, 0, 3746)).toMatchObject({ at: 3746, note: 'Heute: 62:26–89:21.' })
  })

  it('#30: a jump is the playhead going back more than 60 s by itself', () => {
    expect(JUMP).toBe(60)
    expect(jumpedBack(3746, 0)).toBe(true)
    expect(jumpedBack(3746, 3685.5)).toBe(true)
    expect(jumpedBack(3746, 3690)).toBe(false) // ← a line back, R, the loop
    expect(jumpedBack(3746, 3800)).toBe(false) // forward
  })
})

describe('the "gesprochen" track (#29)', () => {
  // Invented lines. Spoken lines sit on the words: gaps of 0–0.1 s are common.
  const SPOKEN = [
    { start: 10.0, end: 11.42, text: 'Da frage ich mich, ob es nicht mal Ärger gab.' },
    { start: 11.42, end: 12.1, text: 'Ich hab das nachgeprüft.' },
    { start: 12.18, end: 13.0, text: 'Und?' },
    { start: 13.0, end: 14.5, text: '♪ Leise Musik ♪' }
  ]
  const ARD = [{ start: 10.2, end: 12.4, text: 'Gab es mal Ärger?' }]
  const media = { cues: ARD, spokenCues: SPOKEN }

  it('is the default whenever the clip has it; ARD on request or without a transcript', () => {
    expect(pickTrack(media, 'spoken')).toEqual({ spoken: true, cues: SPOKEN })
    expect(pickTrack(media, 'ard')).toEqual({ spoken: false, cues: ARD })
    expect(pickTrack({ cues: ARD, spokenCues: null }, 'spoken')).toEqual({ spoken: false, cues: ARD })
    expect(pickTrack({ cues: ARD, spokenCues: [] }, 'spoken').spoken).toBe(false)
    expect(speechCues(pickTrack(media, 'spoken').cues).map((c) => c.text)).not.toContain('♪ Leise Musik ♪')
  })

  it('#18 holds on the tighter lines: the text never switches before the pause', () => {
    const lines = speechCues(SPOKEN)
    expect(shownLine(lines, 11.41)).toBe(0)
    expect(shouldPause(lines, 11.44, null, 11.40)).toBe(0) // overshot a frame into line 1: pause for line 0 …
    expect(shownLine(lines, 11.44, 0)).toBe(0) // … and line 0 stays on screen
    expect(shouldPause(lines, 12.12, 0, 12.08)).toBe(1) // 0.08 s gap
    expect(shownLine(lines, 12.12, 1)).toBe(1)
    expect(shownLine(lines, 12.04)).toBe(1) // still being spoken: stays
    expect(shownLine(lines, 12.12)).toBe(2) // over, in the 0.08 s gap: 'Und?' may come (lead 0.15 s)
  })

  it('switching tracks mid-clip: no immediate pause, the line at the same time', () => {
    expect(shownLine(speechCues(ARD), 11.5)).toBe(0)
    expect(pausedBefore(speechCues(SPOKEN), 11.5)).toBe(0) // in line 1: line 0 counts as heard
    expect(pausedBefore(speechCues(SPOKEN), 12.15)).toBe(1) // in the gap after line 1
    expect(pausedBefore(ARD, 5)).toBe(-1) // before everything: nothing
  })

  it('the choice is remembered per device', () => {
    const v = {}
    const s = { getItem: (k) => v[k] ?? null, setItem: (k, x) => { v[k] = x } }
    expect(storedTrack(s)).toBe('spoken')
    storeTrack('ard', s)
    expect([v['kaskade.schauen.track'], storedTrack(s)]).toEqual(['ard', 'ard'])
    const broken = { getItem() { throw new Error('x') }, setItem() { throw new Error('x') } }
    expect(storedTrack(broken)).toBe('spoken')
    expect(() => storeTrack('ard', broken)).not.toThrow()
  })
})

describe('#34: a line inside its sentence', () => {
  const SPLIT = [
    { start: 1, end: 2, text: 'Wo warst du?' },
    { start: 2.2, end: 3.5, text: 'Mir fällt bei diesem Wetter' },
    { start: 3.5, end: 5, text: 'wirklich nichts mehr ein.' },
    { start: 5.5, end: 6.5, text: 'Gut.' }
  ]

  it('joins the lines of one sentence and says where the line is in it', () => {
    const w = sentenceAround(SPLIT, 2)
    expect(w).toEqual({ text: 'Mir fällt bei diesem Wetter wirklich nichts mehr ein.', focus: [28, 53], from: 1, to: 2, start: 2.2, end: 5 })
    expect(w.text.slice(...w.focus)).toBe('wirklich nichts mehr ein.')
    expect(sentenceAround(SPLIT, 1).focus).toEqual([0, 27])
    expect(sentenceAround(SPLIT, 0)).toMatchObject({ text: 'Wo warst du?', from: 0, to: 0 })
    expect(sentenceAround(SPLIT, 3)).toMatchObject({ text: 'Gut.', start: 5.5, end: 6.5 })
    expect(sentenceAround(SPLIT, 9)).toBe(null)
  })

  it("ARD's trailing dots continue the sentence; a new speaker, a long pause and 3 lines each way stop it", () => {
    expect(endsSentence('Ich bin in den Keller gegangen und...')).toBe(false)
    expect(endsSentence('Er kommt gleich.')).toBe(true)
    expect(endsSentence('„Komm her!“')).toBe(true)
    expect(endsSentence('Ich weiß nicht')).toBe(false)
    const dots = [{ start: 0, end: 1, text: 'Ich bin in den Keller gegangen und...' }, { start: 1, end: 2, text: '...dort stand eine Kiste.' }]
    expect(sentenceAround(dots, 1).text).toBe('Ich bin in den Keller gegangen und... ...dort stand eine Kiste.')
    const speaker = [{ start: 0, end: 1, text: 'Und dann' }, { start: 1, end: 2, text: '- Was dann?' }]
    expect(sentenceAround(speaker, 1).from).toBe(1)
    const pause = [{ start: 0, end: 1, text: 'Und dann' }, { start: 3.5, end: 4, text: 'kam er.' }]
    expect(sentenceAround(pause, 1).from).toBe(1)
    const many = Array.from({ length: 9 }, (_, i) => ({ start: i, end: i + 1, text: `Wort${i}` }))
    expect(sentenceAround(many, 4)).toMatchObject({ from: 1, to: 7 })
  })
})
