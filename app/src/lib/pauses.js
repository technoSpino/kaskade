// "Woche frei nehmen" on the Fahrplan (#36): pure helpers, testable without a browser.
import { dayLabel } from './materials'

/** "Mo 26.10.–So 1.11." */
export function weekLabel(p) {
  return `${dayLabel(p.from)}–${dayLabel(p.to)}`
}

/** What a week off moves, one line each: the plan week in it (and everything after), then the due dates. */
export function moveLines(preview) {
  const w = preview.week
  const lines = [`Woche ${w.n} (${w.theme}) beginnt ${dayLabel(w.now)} statt ${dayLabel(w.was)} — alles danach eine Woche später.`]
  for (const d of preview.due) lines.push(`${d.title}: fällig ${dayLabel(d.now)} statt ${dayLabel(d.was)}`)
  return lines
}
