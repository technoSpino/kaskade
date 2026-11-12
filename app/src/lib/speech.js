// Audio for sentences. Prefers server audio (Piper TTS, M6, or the clip's original voice) and falls
// back to the browser's German speech synthesis.
//
// #28: speak() returns a promise that always settles, so Karten can start its timer when the clip
// is over: 'ended' | 'error' (nothing could play) | 'blocked' (the browser refused to play without a
// click) | 'stopped' (stopSpeaking) | 'replaced' (another speak) | 'timeout' (no end in sight).
// One long-lived <audio> element, its src swapped per card: Safari lets an element play without a
// click only once a click has started it, and the next card arrives after an async fetch. The first
// click/key on the page unlocks it (unlockOnFirstGesture, called from main.js).

export const SAFETY_MS = 1000 // the promise settles at the latest this long after the clip's duration …
export const UNKNOWN_MS = 15_000 // … or after this, while the duration is unknown (browser voice, no metadata yet)

// 10 ms of silence, played inside the first gesture to unlock the element
const SILENT = 'data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA=='

/** `makeAudio`, `synth`, `Utterance` and `timers` are injectable (unit tests run without a browser). */
export function createSpeaker({ makeAudio, synth = null, Utterance = null, timers = globalThis } = {}) {
  let el = null
  let current = null // what is playing now: { settle }
  let unlocked = false
  const audio = () => (el ??= makeAudio())

  function speak(text, { url } = {}) {
    current?.settle('replaced')
    if (synth?.speaking || synth?.pending) synth.cancel()
    let resolve
    const result = new Promise((r) => { resolve = r })
    const off = new AbortController() // listeners of this playback
    let safety = 0
    const me = {
      settle(how) {
        if (current !== me) return
        current = null
        off.abort()
        timers.clearTimeout(safety)
        resolve(how)
      }
    }
    current = me
    const arm = (ms) => {
      timers.clearTimeout(safety)
      safety = timers.setTimeout(() => me.settle('timeout'), ms)
    }
    arm(UNKNOWN_MS)

    const browserVoice = () => {
      if (current !== me) return
      if (!synth || !Utterance) return me.settle('error')
      const u = new Utterance(text)
      u.lang = 'de-DE'
      u.rate = 0.95
      const voice = synth.getVoices?.().find((v) => v.lang?.startsWith('de'))
      if (voice) u.voice = voice
      u.addEventListener('end', () => me.settle('ended'), { signal: off.signal })
      u.addEventListener('error', (e) => me.settle(e.error === 'not-allowed' ? 'blocked' : 'error'), { signal: off.signal })
      arm(UNKNOWN_MS)
      synth.speak(u)
    }
    if (!url) {
      browserVoice()
      return result
    }

    const a = audio()
    const offAudio = new AbortController() // dropped when falling back to the browser voice
    off.signal.addEventListener('abort', () => offAudio.abort())
    const on = (type, fn) => a.addEventListener(type, fn, { signal: offAudio.signal })
    const fallback = () => {
      if (current !== me || offAudio.signal.aborted) return
      offAudio.abort()
      browserVoice()
    }
    const fromDuration = () => {
      if (current === me && !offAudio.signal.aborted && Number.isFinite(a.duration)) {
        arm(Math.max(0, a.duration - (a.currentTime || 0)) * 1000 + SAFETY_MS)
      }
    }
    on('ended', () => me.settle('ended'))
    on('error', fallback)
    on('loadedmetadata', fromDuration)
    on('playing', fromDuration)
    a.src = url
    let played
    try {
      played = Promise.resolve(a.play())
    } catch (e) {
      played = Promise.reject(e)
    }
    played.then(fromDuration, (e) => {
      if (current !== me) return
      if (e?.name === 'NotAllowedError') me.settle('blocked')
      else fallback() // no audio file (404), unsupported format …
    })
    return result
  }

  function stop() {
    current?.settle('stopped')
    if (el && !el.paused) el.pause()
    if (synth?.speaking || synth?.pending) synth.cancel()
  }

  /** Call inside a click/key handler: lets the element play later without one (Safari). */
  function unlock() {
    if (unlocked) return
    const a = audio()
    if (!a.paused) { unlocked = true; return } // playing already: allowed
    a.src = SILENT
    let played
    try {
      played = Promise.resolve(a.play())
    } catch (e) {
      played = Promise.reject(e)
    }
    played.then(() => {
      unlocked = true
      if (a.src === SILENT) a.pause()
    }, () => {}) // replaced by a card's audio in the same gesture, or refused: the next gesture tries again
  }

  return { speak, stop, unlock, get unlocked() { return unlocked } }
}

/**
 * #28: resolves when the audio is over — following a replay that replaced it (A during the clip),
 * so that isn't counted either. `latest()` returns the newest speak() promise.
 */
export async function playbackOver(latest) {
  let p = latest()
  for (;;) {
    const how = await p
    const next = latest()
    if (how !== 'replaced' || !next || next === p) return how
    p = next
  }
}

export function canSpeak() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

const speaker = createSpeaker({
  makeAudio: () => new Audio(),
  synth: canSpeak() ? window.speechSynthesis : null,
  Utterance: typeof window !== 'undefined' ? window.SpeechSynthesisUtterance ?? null : null
})

export const speak = (text, opts) => speaker.speak(text, opts)
export const stopSpeaking = () => speaker.stop()

/** The first click or key anywhere on the page unlocks the audio element (capture phase: before the page's own handlers). */
export function unlockOnFirstGesture(target = window) {
  const handler = () => {
    speaker.unlock()
    if (speaker.unlocked) {
      target.removeEventListener('pointerdown', handler, true)
      target.removeEventListener('keydown', handler, true)
    }
  }
  target.addEventListener('pointerdown', handler, true)
  target.addEventListener('keydown', handler, true)
}
