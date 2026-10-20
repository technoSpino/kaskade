import { describe, expect, it } from 'vitest'
import { bookLine, dayLabel, dueFor, dueLabel, groupTitle, itemLine, noticeTitle, STATUS_LABEL, withinDays, withSecureCheck } from '../../lib/materials'

describe('Material für heute und morgen', () => {
  it('titles the groups: today, tomorrow, next plan day', () => {
    expect(dayLabel('2026-10-12')).toBe('Mo 12.10.')
    expect(groupTitle({ kind: 'today', date: '2026-10-11' })).toBe('Heute (So 11.10.)')
    expect(groupTitle({ kind: 'tomorrow', date: '2026-10-12' })).toBe('Morgen (Mo 12.10.)')
    expect(groupTitle({ kind: 'next', date: '2026-10-19' })).toBe('Nächster Lerntag: Mo 19.10.')
  })

  it('needs HTTPS for the microphone, nothing else changes', () => {
    const mic = { check: 'secure', status: 'ready', detail: 'Mikrofon / Headset' }
    const url = 'https://cos.tail1b5741.ts.net:8443'
    expect(withSecureCheck(mic, true, url)).toMatchObject({ status: 'ready', detail: 'Mikrofon / Headset · Mikrofon geht hier ✓' })
    const http = withSecureCheck(mic, false, url)
    expect(http.status).toBe('todo')
    expect(http.detail).toBe(`Mikrofon / Headset — Aufnahmen gehen nur über ${url}`)
    expect(http.fix.href).toBe(url)
    const clip = { status: 'ready', detail: 'in deiner Bibliothek' }
    expect(withSecureCheck(clip, false, url)).toBe(clip)
    expect(STATUS_LABEL).toEqual({ ready: '✓ bereit', todo: '→ zu tun' })
  })

  it('names notices and items exactly', () => {
    expect(noticeTitle({ type: 'book', by: '2026-10-12' })).toBe('Kaufen bis Mo, 12.10.')
    expect(noticeTitle({ type: 'setup', by: '2026-10-21' })).toBe('Einrichten bis Mi, 21.10.')
    expect(itemLine({ title: 'Tatort: Schweigen', part: '0:00–30:14', minutes: 30 })).toBe('Tatort: Schweigen · 0:00–30:14 · 30 min')
    expect(itemLine({ title: 'Fällige Karten', part: '12 fällig + 20 neu', minutes: null })).toBe('Fällige Karten · 12 fällig + 20 neu')
  })
})

describe('notices on Heute', () => {
  it('shows what is due within two weeks (and anything overdue)', () => {
    expect(withinDays('2026-10-12', '2026-10-11', 14)).toBe(true)
    expect(withinDays('2026-10-25', '2026-10-11', 14)).toBe(true)
    expect(withinDays('2026-10-26', '2026-10-11', 14)).toBe(false)
    expect(withinDays('2026-10-05', '2026-10-11', 14)).toBe(true)
  })
})

describe('Bald fällig', () => {
  it('puts the due date first, relative to today', () => {
    expect(dueLabel('2026-10-12', '2026-10-11')).toEqual({ text: 'Fällig Mo 12.10. · morgen', overdue: false })
    expect(dueLabel('2026-10-17', '2026-10-11')).toEqual({ text: 'Fällig Sa 17.10. · in 6 Tagen', overdue: false })
    expect(dueLabel('2026-10-11', '2026-10-11').text).toBe('Fällig So 11.10. · heute')
    expect(dueLabel('2026-10-12', '2026-10-16')).toEqual({ text: 'Überfällig seit Mo 12.10.', overdue: true })
  })

  it('says what it is for', () => {
    expect(dueFor({ firstDay: '2026-10-19', week: 2 })).toBe('ab 19.10. im Plan, Woche 2')
  })

  it('names the edition to buy: paper by ISBN, a Kindle ebook by its label and ASIN (#32)', () => {
    const paper = { format: 'paper', isbn: '978-3-442-77066-3', price: '12,00 €' }
    expect(bookLine(paper, ', ')).toBe('Taschenbuch, ISBN 978-3-442-77066-3, 12,00 €')
    expect(bookLine(paper)).toBe('Taschenbuch · ISBN 978-3-442-77066-3 · 12,00 €')
    const kindle = { format: 'ebook', formatLabel: 'Kindle-E-Book (Dunkle Edition)', isbn: '978-3-8437-1597-3', asin: 'B071436DMF', price: '9,99 €' }
    expect(bookLine(kindle)).toBe('Kindle-E-Book (Dunkle Edition) · ASIN B071436DMF · 9,99 €')
    expect(bookLine({ format: 'ebook', isbn: '978-0-00-000000-0', price: '5,00 €' })).toBe('E-Book · ISBN 978-0-00-000000-0 · 5,00 €')
  })
})
