// WCAG contrast check for every theme in themes.css. If a pair fails, change
// the colour in themes.css — never the threshold.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { THEMES } from '../../lib/theme'

const CSS = readFileSync(join(__dirname, '..', '..', 'styles', 'themes.css'), 'utf-8')

const REQUIRED = [
  'bg', 'surface', 'surface-2', 'border', 'border-width', 'text', 'text-2', 'muted', 'primary', 'primary-text',
  'accent', 'accent-text', 'word-new-bg', 'word-learning', 'focus', 'radius-sm', 'radius-lg', 'shadow',
  'font-ui', 'font-heading', 'font-read', 'font-size-base', 'case-n', 'case-a', 'case-d', 'case-g',
  'case-n-bg', 'case-a-bg', 'case-d-bg', 'case-g-bg', 'chart-active', 'chart-passive',
  'timeline-upcoming', 'timeline-upcoming-border', 'timeline-text', 'timeline-current', 'timeline-current-text', 'timeline-current-border',
  'timeline-done', 'timeline-done-text', 'timeline-pause', 'timeline-pause-line', 'word-new-tint', 'word-new-underline',
  'origin-ai-bg', 'origin-ai-text', 'origin-ai-border'
]

/** { themeId: { token: value } } parsed from the :root[data-theme='x'] blocks. */
export function parseThemes(css) {
  const out = {}
  const re = /((?::root(?:\[data-theme='[a-z]+'\])?,?\s*)+)\{([^}]*)\}/g
  let m
  while ((m = re.exec(css))) {
    const ids = [...m[1].matchAll(/data-theme='([a-z]+)'/g)].map((x) => x[1])
    if (!ids.length || /\.\w/.test(m[1])) continue
    const tokens = {}
    for (const d of m[2].matchAll(/--([\w-]+):\s*([^;]+);/g)) tokens[d[1]] = d[2].trim()
    for (const id of ids) out[id] = tokens
  }
  return out
}

function luminance(hex) {
  let h = hex.replace('#', '')
  if (h.length === 3) h = [...h].map((c) => c + c).join('')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

const themes = parseThemes(CSS)

describe('contrast helper', () => {
  it('matches known WCAG values', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 0)
    expect(contrast('#777777', '#ffffff')).toBeCloseTo(4.48, 1)
  })
})

describe('themes.css', () => {
  it('defines all six themes', () => {
    expect(Object.keys(themes).sort()).toEqual(THEMES.map((t) => t.id).sort())
  })

  for (const { id } of THEMES) {
    describe(id, () => {
      const t = themes[id] ?? {}

      it('defines every required token', () => {
        expect(REQUIRED.filter((k) => !(k in t))).toEqual([])
      })

      const pairs = [
        ['text', 'bg', 4.5], ['text', 'surface', 4.5], ['text-2', 'surface', 4.5],
        ['muted', 'bg', 4.5], ['muted', 'surface', 4.5],
        ['primary-text', 'primary', 4.5], ['accent-text', 'accent', 4.5],
        ['text', 'word-new-bg', 4.5], ['text-2', 'callout', 4.5], ['kicker', 'surface', 4.5],
        ['link', 'surface', 4.5], ['nav-text', 'nav-bg', 4.5], ['nav-muted', 'nav-bg', 4.5],
        ['stage-text', 'stage-bg', 4.5], ['success', 'success-bg', 4.5],
        // Heute timeline: label on each segment state, and the segments themselves as UI marks
        ['timeline-text', 'timeline-upcoming', 4.5], ['timeline-current-text', 'timeline-current', 4.5],
        ['timeline-done-text', 'timeline-done', 4.5], ['timeline-upcoming-border', 'surface', 3], ['timeline-current-border', 'surface', 3],
        // reader: new words as a light tint + underline
        ['text', 'word-new-tint', 4.5], ['word-new-underline', 'surface', 3],
        // "KI-geschrieben" badge: text on its tint, outline visible on cards
        ['origin-ai-text', 'origin-ai-bg', 4.5], ['origin-ai-text', 'surface', 4.5], ['origin-ai-border', 'surface', 3],
        ['focus', 'bg', 3], ['word-learning', 'surface', 3], ['chart-active', 'surface', 3], ['chart-passive', 'surface', 3],
        ...['n', 'a', 'd', 'g'].flatMap((c) => [[`case-${c}`, `case-${c}-bg`, 4.5], [`case-${c}`, 'surface', 4.5]])
      ]
      it.each(pairs)('%s on %s ≥ %s:1', (fg, bg, min) => {
        expect(t[fg], `missing --${fg}`).toMatch(/^#/)
        expect(t[bg], `missing --${bg}`).toMatch(/^#/)
        expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(min)
      })
    })
  }
})
