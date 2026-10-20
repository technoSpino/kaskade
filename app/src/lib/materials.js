// "Material für heute und morgen" on Heute (#16): pure helpers, testable without a browser.

const WEEKDAY = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']

/** "2026-10-12" → "Mo 12.10." */
export function dayLabel(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const wd = WEEKDAY[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]
  return `${wd} ${d}.${m}.`
}

/** Heading of a group: "Heute (So 11.10.)", "Morgen (Mo 12.10.)", "Nächster Lerntag: Mo 19.10." */
export function groupTitle(group) {
  if (group.kind === 'today') return `Heute (${dayLabel(group.date)})`
  if (group.kind === 'tomorrow') return `Morgen (${dayLabel(group.date)})`
  return `Nächster Lerntag: ${dayLabel(group.date)}`
}

/**
 * The microphone works only in a secure context (HTTPS, or localhost). Items that need it
 * (Sprechen, Probeprüfung) become "zu tun" over plain http, with the HTTPS address as the fix.
 */
export function withSecureCheck(item, secure, httpsUrl) {
  if (item.check !== 'secure') return item
  if (secure) return { ...item, detail: `${item.detail} · Mikrofon geht hier ✓` }
  return { ...item, status: 'todo', detail: `${item.detail} — Aufnahmen gehen nur über ${httpsUrl}`, fix: { href: httpsUrl, label: 'Über HTTPS öffnen' } }
}

export const STATUS_LABEL = { ready: '✓ bereit', todo: '→ zu tun' }

/** "Kaufen bis Mo, 19.10." / "Einrichten bis Mi, 21.10." */
export function noticeTitle(n) {
  const [y, m, d] = n.by.split('-').map(Number)
  const wd = WEEKDAY[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]
  return `${n.type === 'book' ? 'Kaufen' : 'Einrichten'} bis ${wd}, ${d}.${m}.`
}

const daysBetween = (from, to) => Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000)

/**
 * "Bald fällig" (#16 Update 6): the due date first — "Fällig Mo 12.10. · morgen",
 * "Fällig Sa 17.10. · in 6 Tagen", "Überfällig seit Mo 12.10.".
 */
export function dueLabel(by, today) {
  const n = daysBetween(today, by)
  if (n < 0) return { text: `Überfällig seit ${dayLabel(by)}`, overdue: true }
  const when = n === 0 ? 'heute' : n === 1 ? 'morgen' : `in ${n} Tagen`
  return { text: `Fällig ${dayLabel(by)} · ${when}`, overdue: false }
}

/** What it's for: "ab 19.10. im Plan, Woche 2" */
export function dueFor(n) {
  const [, m, d] = n.firstDay.split('-').map(Number)
  return `ab ${d}.${m}. im Plan, Woche ${n.week}`
}

/**
 * Which edition to buy (#32): "Taschenbuch · ISBN 978-3-442-77066-3 · 12,00 €",
 * an ebook with its label and ASIN: "Kindle-E-Book (Dunkle Edition) · ASIN B071436DMF · 9,99 €".
 */
export function bookLine(b, sep = ' · ') {
  const what = b.format === 'ebook' ? [b.formatLabel ?? 'E-Book', b.asin ? `ASIN ${b.asin}` : `ISBN ${b.isbn}`] : ['Taschenbuch', `ISBN ${b.isbn}`]
  return [...what, b.price].join(sep)
}

/** One line of what an item is: "Tatort: Schweigen · 0:00–30:14 · 30 min" */
export function itemLine(item) {
  return [item.title, item.part, item.minutes ? `${item.minutes} min` : null].filter(Boolean).join(' · ')
}

/** Whether the ISO date `by` is at most `days` after `today` (overdue counts too). */
export function withinDays(by, today, days) {
  return (Date.parse(`${by}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86400000 <= days
}
