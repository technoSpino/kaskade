// German number/date formatting helpers.

export function formatNumber(n) {
  return new Intl.NumberFormat('de-DE').format(Math.round(n))
}

export function formatHours(seconds) {
  const h = seconds / 3600
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(h) + ' h'
}

export function formatDate(iso) {
  return new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(iso))
}

export function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function formatDecimal(n, digits = 1) {
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: digits }).format(n)
}
