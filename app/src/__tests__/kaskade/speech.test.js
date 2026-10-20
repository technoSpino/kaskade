import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSpeaker, playbackOver, SAFETY_MS, UNKNOWN_MS } from '../../lib/speech'
import { createRevealTimer } from '../../lib/reveal'

// A stand-in for <audio>: play() does what `next` says.
class FakeAudio extends EventTarget {
  constructor() {
    super()
    this.paused = true
    this.duration = NaN
    this.currentTime = 0
    this.src = ''
    this.next = 'ok' // ok | NotAllowedError | NotSupportedError | throw
    this.plays = []
  }
  play() {
    this.plays.push(this.src)
    if (this.next === 'throw') throw new Error('kaputt')
    if (this.next !== 'ok') return Promise.reject(Object.assign(new Error(this.next), { name: this.next }))
    this.paused = false
    return Promise.resolve()
  }
  pause() { this.paused = true }
  fire(type) { if (type === 'ended') this.paused = true; this.dispatchEvent(new Event(type)) }
}

class FakeUtterance extends EventTarget {
  constructor(text) { super(); this.text = text }
}

function fakeSynth() {
  return { speaking: false, pending: false, said: [], cancel: vi.fn(), getVoices: () => [{ lang: 'de-DE' }], speak(u) { this.said.push(u) } }
}

let el, synth, speaker
beforeEach(() => {
  vi.useFakeTimers()
  el = new FakeAudio()
  synth = fakeSynth()
  speaker = createSpeaker({ makeAudio: () => el, synth, Utterance: FakeUtterance })
})
afterEach(() => vi.useRealTimers())

/** What Karten does when a card comes up: play, and start the timer only when the audio is over. */
function showCard(timer, url = '/api/cards/core:r00001/audio') {
  let latest = speaker.speak('Ich habe heute keine Zeit.', { url })
  const over = playbackOver(() => latest).then((how) => { timer.start(); return how })
  return { over, replay: () => { latest = speaker.speak('Ich habe heute keine Zeit.', { url }) } }
}

describe('autoplay (#28): the timer waits for the audio', () => {
  it('does not run while the clip plays and starts on "ended"', async () => {
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    await vi.advanceTimersByTimeAsync(3000)
    expect(timer.running).toBe(false)
    expect(el.src).toBe('/api/cards/core:r00001/audio')
    el.fire('ended')
    expect(await over).toBe('ended')
    expect(timer.running).toBe(true)
  })

  it('starts right away when the browser refuses to play without a click', async () => {
    el.next = 'NotAllowedError'
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    expect(await over).toBe('blocked')
    expect(timer.running).toBe(true)
    expect(synth.said).toEqual([]) // no browser voice either: "A drücken"
  })

  it('no audio file: the browser voice speaks, and the timer starts at its end', async () => {
    el.next = 'NotSupportedError'
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    await vi.advanceTimersByTimeAsync(0)
    expect(synth.said.map((u) => [u.text, u.lang])).toEqual([['Ich habe heute keine Zeit.', 'de-DE']])
    expect(timer.running).toBe(false)
    synth.said[0].dispatchEvent(new Event('end'))
    expect(await over).toBe('ended')
    expect(timer.running).toBe(true)
  })

  it('an error on the element falls back once; a browser voice error ends it', async () => {
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    await vi.advanceTimersByTimeAsync(0)
    el.fire('error')
    el.fire('error')
    expect(synth.said).toHaveLength(1)
    synth.said[0].dispatchEvent(Object.assign(new Event('error'), { error: 'synthesis-failed' }))
    expect(await over).toBe('error')
    expect(timer.running).toBe(true)
  })

  it('without any voice it fails at once, and play() throwing is no exception', async () => {
    const mute = createSpeaker({ makeAudio: () => el })
    el.next = 'throw'
    expect(await mute.speak('Hallo.', { url: '/x' })).toBe('error')
    expect(await mute.speak('Hallo.')).toBe('error')
  })

  it('safety: 15 s while the duration is unknown …', async () => {
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    await vi.advanceTimersByTimeAsync(UNKNOWN_MS - 1)
    expect(timer.running).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(await over).toBe('timeout')
    expect(timer.running).toBe(true)
  })

  it('… and the clip’s duration + 1 s once it is known', async () => {
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    el.duration = 3.2
    el.fire('loadedmetadata')
    await vi.advanceTimersByTimeAsync(3200 + SAFETY_MS - 1)
    expect(timer.running).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(await over).toBe('timeout')
  })

  it('A during the clip: the replay is not counted either', async () => {
    const timer = createRevealTimer()
    const { over, replay } = showCard(timer)
    await vi.advanceTimersByTimeAsync(1000)
    replay()
    await vi.advanceTimersByTimeAsync(1000)
    expect(timer.running).toBe(false)
    expect(el.plays).toHaveLength(2)
    el.fire('ended')
    expect(await over).toBe('ended')
    expect(timer.running).toBe(true)
  })

  it('stop (box unticked, Karten left): the audio stops and the timer starts', async () => {
    const timer = createRevealTimer()
    const { over } = showCard(timer)
    await vi.advanceTimersByTimeAsync(500)
    speaker.stop()
    expect(el.paused).toBe(true)
    expect(await over).toBe('stopped')
    expect(timer.running).toBe(true)
  })

  it('a late "ended" of the previous card settles nothing of the next', async () => {
    const first = speaker.speak('Eins.', { url: '/a' })
    const second = speaker.speak('Zwei.', { url: '/b' })
    expect(await first).toBe('replaced')
    el.fire('ended')
    expect(await second).toBe('ended')
    let third = 'pending'
    speaker.speak('Drei.', { url: '/c' }).then((how) => { third = how })
    await vi.advanceTimersByTimeAsync(0)
    expect(third).toBe('pending')
  })
})

describe('unlocking the player in the first gesture (Safari)', () => {
  it('plays a moment of silence once, then stays unlocked', async () => {
    speaker.unlock()
    expect(el.src).toMatch(/^data:audio\/wav;base64,/)
    await vi.advanceTimersByTimeAsync(0)
    expect(speaker.unlocked).toBe(true)
    expect(el.paused).toBe(true)
    speaker.unlock()
    expect(el.plays).toHaveLength(1)
  })
  it('never cuts a card’s audio', async () => {
    speaker.speak('Hallo.', { url: '/a' }) // playing
    speaker.unlock()
    expect(el.src).toBe('/a')
    expect(speaker.unlocked).toBe(true)
    // the card's audio arrives in the same gesture, after the silence started
    const s2 = createSpeaker({ makeAudio: () => el })
    el.paused = true
    s2.unlock()
    el.src = '/b'
    await vi.advanceTimersByTimeAsync(0)
    expect(el.paused).toBe(false)
  })
  it('refused: the next gesture tries again', async () => {
    el.next = 'NotAllowedError'
    speaker.unlock()
    await vi.advanceTimersByTimeAsync(0)
    expect(speaker.unlocked).toBe(false)
    el.next = 'ok'
    speaker.unlock()
    await vi.advanceTimersByTimeAsync(0)
    expect(speaker.unlocked).toBe(true)
  })
})
