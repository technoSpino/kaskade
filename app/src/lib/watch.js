// Pure helpers for "Schauen & minen": subtitle navigation, testable without a browser.

const WRAPPED = /^\s*(?:\*[^*]*\*|\[[^\]]*\]|\([^)]*\))\s*$/
const MUSIK = /^musik\.?$/i // #30: Whisper's word for a theme tune, not a line of dialogue

/** Sound/music cues, not speech: fully wrapped in *…*, […] or (…), starting with ♪, or only "Musik" (same rule as the server). */
export function isNonSpeech(text) {
  const t = (text ?? '').trim()
  return !t || /^[♪♫#]/.test(t) || WRAPPED.test(t) || MUSIK.test(t)
}

/** Only the cues that are speech. */
export const speechCues = (cues) => cues.filter((c) => !isNonSpeech(c.text))

/** Index of the last cue that started at or before `t` (-1 before the first). Cues are sorted by start. */
export function lineAt(cues, t) {
  let lo = 0
  let hi = cues.length - 1
  let found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (cues[mid].start <= t + 0.001) {
      found = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return found
}

/** Whether `t` is inside cue `i` (its spoken part). */
export const inside = (cues, i, t) => i >= 0 && t >= cues[i].start && t < cues[i].end

/** How far ahead the next line may appear — only inside a real gap between lines. */
export const LEAD = 0.15

/**
 * The line to show at `t` (#18): a line being spoken stays until its end; only in a gap
 * does the next line appear up to `lead` early (never earlier than that). `held` = the line
 * auto-pause stopped after: it stays on screen until play resumes or he navigates.
 */
export function shownLine(cues, t, held = -1, lead = LEAD) {
  if (held >= 0 && held < cues.length) return held
  const i = lineAt(cues, t)
  if (i >= 0 && t < cues[i].end) return i
  return lineAt(cues, t + lead)
}

/** Target line for ← / → from the shown line `i`. */
export function stepLine(cues, i, dir) {
  if (!cues.length) return -1
  if (dir > 0) return Math.min(cues.length - 1, i + 1)
  return Math.max(0, i - 1)
}

/** Where to seek for line `i`: 0.1 s before it, but never back into the previous line. */
export function seekTarget(cues, i) {
  const c = cues[i]
  const prevEnd = i > 0 ? cues[i - 1].end : 0
  return Math.max(0, Math.min(c.start, Math.max(c.start - 0.1, prevEnd)))
}

/**
 * Auto-pause: once the playhead passes the end of line `i`, pause — but only once per
 * line, so pressing play again continues to the next line. `prev` is the playhead at the
 * last tick: with lines only a frame apart it may already be in the next line, and the
 * line whose end it just crossed is the one to pause for.
 */
export function shouldPause(cues, t, pausedFor, prev) {
  const i = lineAt(cues, t)
  if (i < 0) return -1
  if (t >= cues[i].end) return i === pausedFor ? -1 : i
  const k = i - 1
  const crossed = prev !== undefined && k >= 0 && prev < cues[k].end && cues[k].end <= t && t - prev < 0.5
  return crossed && k !== pausedFor ? k : -1
}

/** Where to resume: the saved position, unless it's (almost) at the very end. */
export function resumeAt(position, duration) {
  if (!position || position < 2) return 0
  if (duration && position > duration - 5) return 0
  return position
}

/** 754 → "12:34", 5361 → "1:29:21". */
export function formatTime(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const pad = (n) => String(n).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`
}

/** Plan range times as minutes:seconds, also past an hour ("89:21") — like the plan texts. */
export function clock(sec) {
  const s = Math.max(0, Math.round(sec || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/**
 * Where a plan range starts (Heute "Starten" → /schauen/ID?von=…&bis=…) and what to tell Matt:
 * behind → from his position; inside the range → resume; already past the end → "Ziel erreicht".
 * `prevReached` = how far the clip's previous plan range got (#30): if that was already at `from`, a
 * saved position before it went backwards afterwards (a jump) and must not pull him back.
 */
export function rangeStart(from, to, position, prevReached = null) {
  const pos = position || 0
  if (to && pos > from && pos >= to - 5) return { at: pos, reached: true, note: `Ziel für heute (bis ${clock(to)}) schon erreicht — du kannst weiterschauen.` }
  if (pos > 2 && pos < from - 5) {
    if (prevReached != null && prevReached >= from) return { at: from, reached: false, note: `Heute: ${clock(from)}–${clock(to)} (zuletzt gespeichert: ${clock(Math.floor(pos))}).` }
    return { at: pos, reached: false, note: `Ab deiner Position (${clock(pos)}) bis ${clock(to)}.` }
  }
  if (pos > from + 5) return { at: pos, reached: false, note: `Weiter ab ${clock(pos)} bis ${clock(to)}.` }
  return { at: from, reached: false, note: `Heute: ${clock(from)}–${clock(to)}.` }
}

/** #30: how far back the playhead may move by itself before it counts as a jump (← and chosen lines don't count). */
export const JUMP = 60

/** Whether the playhead went from `known` to `now` by a jump back (> 60 s). */
export const jumpedBack = (known, now) => known - now > JUMP

/** Note for a clip whose file is being converted to H.264/AAC MP4, or whose conversion failed. */
export function clipStatus(clip) {
  if (clip?.status === 'converting') return 'wird für alle Browser umgewandelt …'
  if (clip?.status === 'original') return 'Originaldatei (Umwandlung fehlgeschlagen — spielt evtl. nicht in Safari)'
  return ''
}

const MB = 1024 * 1024
const mb = (b) => new Intl.NumberFormat('de-DE', { maximumFractionDigits: b < 10 * MB ? 1 : 0 }).format(b / MB)

/** Progress line of a Mediathek download job, e.g. "38 von 145 MB · 7,9 MB/s". */
export function jobLabel(job) {
  if (!job) return ''
  if (job.status === 'done') return 'Fertig.'
  if (job.status === 'error') return job.message || 'Fehlgeschlagen.'
  if (job.phase === 'convert') return 'Wird für alle Browser vorbereitet …'
  if (!job.downloaded) return 'Verbinde mit der Mediathek …'
  const size = job.total ? `${mb(job.downloaded)} von ${mb(job.total)} MB` : `${mb(job.downloaded)} MB`
  return job.speed ? `${size} · ${mb(job.speed)} MB/s` : size
}

// #29: the "gesprochen" track (Whisper, what is actually said) or ARD's subtitles (condensed).
const TRACK_KEY = 'kaskade.schauen.track'

/** 'spoken' (default) or 'ard', remembered per device; missing or blocked storage → 'spoken'. */
export function storedTrack(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(TRACK_KEY) === 'ard' ? 'ard' : 'spoken'
  } catch {
    return 'spoken'
  }
}

export function storeTrack(track, storage = globalThis.localStorage) {
  try {
    storage?.setItem(TRACK_KEY, track)
  } catch {
    // private mode: back to the default next time
  }
}

/** The cues to show: the spoken track whenever the clip has one and he didn't pick ARD's. */
export function pickTrack(media, pref) {
  const spoken = pref !== 'ard' && media?.spokenCues?.length > 0
  return { spoken, cues: (spoken ? media.spokenCues : media?.cues) ?? [] }
}

/**
 * After switching tracks at `t`: the line auto-pause counts as done for — the last one that already
 * ended (so play doesn't stop again at once), or the one before the line being spoken.
 */
export function pausedBefore(cues, t) {
  const i = lineAt(cues, t)
  if (i < 0) return -1
  return t >= cues[i].end ? i : i - 1
}

// #34: a line is analysed (and mined) inside its whole sentence — the verb and its prefix can be on
// different lines (fällt … | … ein), and a cut line changes the parse.
const SENTENCE_END = /[.?!][")»«“”'’]*$/
const NEW_SPEAKER = /^[-–]\s/
export const SENTENCE_CUES = 3 // at most this many neighbouring lines each way
export const SENTENCE_GAP = 2 // s: never across a longer silence

/** Does a subtitle line end a sentence? A trailing "..." / "…" is ARD's "continued on the next line". */
export const endsSentence = (text) => SENTENCE_END.test(text.trim()) && !/(\.\.\.|…)[")»«“”'’]*$/.test(text.trim())

/**
 * The sentence around line `i`: neighbouring lines up to a sentence end, at most SENTENCE_CUES each way,
 * not across a pause > SENTENCE_GAP or a new speaker ("- …"). Returns the joined text, the line's
 * character range in it (`focus`) and the time range from the first to the last line.
 */
export function sentenceAround(cues, i, max = SENTENCE_CUES) {
  const c = cues[i]
  if (!c) return null
  const joins = (a, b) => !endsSentence(a.text) && !NEW_SPEAKER.test(b.text.trim()) && b.start - a.end <= SENTENCE_GAP
  let from = i
  let to = i
  while (from > 0 && i - from < max && joins(cues[from - 1], cues[from])) from--
  while (to < cues.length - 1 && to - i < max && joins(cues[to], cues[to + 1])) to++
  const parts = cues.slice(from, to + 1).map((x) => x.text.trim())
  const at = parts.slice(0, i - from).reduce((n, p) => n + p.length + 1, 0)
  return {
    text: parts.join(' '),
    focus: [at, at + parts[i - from].length],
    from,
    to,
    start: cues[from].start,
    end: cues[to].end
  }
}
