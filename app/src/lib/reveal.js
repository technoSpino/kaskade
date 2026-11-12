// Karten (#25): the rating comes from the time to reveal, and the progress counts cards, not presses.
// #28: the time is on the card, and with autoplay it starts only when the sentence's audio is over.

export const CAP_MS = 60_000
export const DOUBLE_TAP_MS = 400 // a second Leertaste/Enter this soon after revealing is ignored
export const GRADE_LABEL = { 1: 'Nochmal', 2: 'Schwer', 3: 'Gut', 4: 'Leicht' }

/**
 * Time from showing a card to revealing it. Runs only while the tab is visible and the window
 * has focus (pause()/resume()), stops on reveal, never more than 60 s. `now` is injectable.
 */
export function createRevealTimer(now = () => performance.now()) {
  let elapsed = 0
  let since = null // running since (ms), or null while paused/stopped
  return {
    start() { elapsed = 0; since = now() },
    /** Back to 0:00, not running (while the card's audio plays). */
    reset() { elapsed = 0; since = null },
    pause() { if (since != null) { elapsed += now() - since; since = null } },
    resume() { if (since == null) since = now() },
    /** Stop and return the time in ms (capped). */
    stop() { this.pause(); return Math.min(CAP_MS, Math.round(elapsed)) },
    get ms() { return Math.min(CAP_MS, Math.round(elapsed + (since != null ? now() - since : 0))) },
    get running() { return since != null }
  }
}

/** "Gewusst" → Leicht (4), Gut (3) or Schwer (2) from the time it took, with the server's thresholds. */
export function grade(ms, timing) {
  if (!timing) return 3
  if (ms <= timing.easyMs) return 4
  if (ms <= timing.hardMs) return 3
  return 2
}

/** The bar and its text: cards done today against cards still open today (steps included). */
export function progress(counts) {
  const done = counts?.doneToday ?? 0
  const left = counts?.left ?? 0
  const total = done + left
  return { done, left, pct: total ? Math.round((done / total) * 100) : 100, text: `${done} fertig · ${left} offen` }
}

/** "Noch 3 Karten — kommen in 6 Min wieder" while every open card waits in a step. */
export function waitLine(wait, now) {
  if (!wait) return null
  const s = Math.max(0, Math.ceil((Date.parse(wait.at) - now) / 1000))
  const when = s >= 60 ? `${Math.ceil(s / 60)} Min` : `${s} s`
  const n = wait.cards === 1 ? 'Noch 1 Karte — kommt' : `Noch ${wait.cards} Karten — kommen`
  return `${n} in ${when} wieder`
}

/** "0:07" while it runs, "60 s+" from the cap on. */
export function runningTime(ms) {
  if (ms >= CAP_MS) return '60 s+'
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** "7,3 s" once revealed (tenths, cut not rounded, so it never shows more than the running time). */
export function finalTime(ms) {
  if (ms >= CAP_MS) return '60 s+'
  return `${(Math.floor(ms / 100) / 10).toFixed(1).replace('.', ',')} s`
}

/**
 * The timer on the card. `phase`: 'audio' (autoplay clip, not counted), 'run', 'pause' (window
 * without focus) or 'done' (revealed). Next to the time, what "Gewusst" would mean right now.
 */
export function clockText(ms, phase, timing) {
  if (phase === 'audio') return '0:00 · Audio'
  const time = phase === 'done' ? finalTime(ms) : runningTime(ms)
  if (phase === 'pause') return `${time} · pausiert`
  return `${time} · ${GRADE_LABEL[grade(ms, timing)]}`
}

// #28 "Audio automatisch abspielen": on unless he switched it off; missing or blocked storage → on
const AUTOPLAY_KEY = 'kaskade.karten.autoplay'

export function storedAutoplay(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(AUTOPLAY_KEY) !== '0'
  } catch {
    return true
  }
}

export function storeAutoplay(on, storage = globalThis.localStorage) {
  try {
    storage?.setItem(AUTOPLAY_KEY, on ? '1' : '0')
  } catch {
    // private mode / blocked storage: on again next time
  }
}
