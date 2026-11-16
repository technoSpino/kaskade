// Hard rule 9: Kaskade components take colours, fonts, radii and shadows from
// theme tokens only — no hex values or font names in component files.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..', '..')
const DIRS = ['components/kaskade', 'views/kaskade']
const FONTS = /(Archivo|Literata|Source Serif|Atkinson|Libre Franklin|Georgia|Helvetica|Arial)/

function files(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    return statSync(p).isDirectory() ? files(p) : p.endsWith('.vue') || p.endsWith('.js') ? [p] : []
  })
}

describe('theme rule', () => {
  const all = DIRS.flatMap((d) => files(join(SRC, d)))

  it('finds the Kaskade components', () => {
    expect(all.length).toBeGreaterThan(2)
  })

  it.each(all.map((f) => [f.slice(SRC.length + 1), f]))('%s has no hex colours or font names', (_, f) => {
    const text = readFileSync(f, 'utf-8')
    expect(text.match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull()
    expect(text.match(FONTS)).toBeNull()
    expect(text.match(/rgba?\(/g)).toBeNull()
  })
})
