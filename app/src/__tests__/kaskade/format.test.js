import { describe, expect, it } from 'vitest'
import { formatClock, formatDecimal, formatHours, formatNumber } from '../../lib/format'

describe('format', () => {
  it('uses German thousands separators', () => {
    expect(formatNumber(1850)).toBe('1.850')
    expect(formatNumber(420.4)).toBe('420')
  })

  it('formats hours with a decimal comma', () => {
    expect(formatHours(3600 * 13.1)).toBe('13,1 h')
    expect(formatHours(0)).toBe('0,0 h')
  })

  it('formats decimals German-style', () => {
    expect(formatDecimal(11.6667)).toBe('11,7')
    expect(formatDecimal(12)).toBe('12')
  })

  it('formats clock times', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(130.9)).toBe('2:10')
    expect(formatClock(-5)).toBe('0:00')
  })
})
