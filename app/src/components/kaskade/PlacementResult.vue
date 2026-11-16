<script setup>
import { formatNumber } from '../../lib/format'

defineProps({ result: { type: Object, required: true } })

const skills = [
  { key: 'lesen', label: 'Lesen' },
  { key: 'hoeren', label: 'Hören (aus dem Satz-Check)' },
  { key: 'schreiben', label: 'Schreiben' },
  { key: 'sprechen', label: 'Sprechen' }
]
</script>

<template>
  <div class="flex flex-col gap-6" data-testid="placement-result">
    <section class="k-card k-card-strong flex flex-wrap gap-8 items-end">
      <div>
        <p class="k-eyebrow">Deine Phase</p>
        <p class="m-0" style="font-size: 56px; font-weight: 800; line-height: 1">{{ result.phase }}</p>
      </div>
      <div>
        <p class="k-eyebrow">Wörter bekannt</p>
        <p class="m-0" style="font-size: 32px; font-weight: 800">{{ result.words != null ? '≈ ' + formatNumber(result.words) : '—' }}</p>
        <p v-if="result.coreKnown != null" class="k-small m-0">davon ≈ {{ formatNumber(result.coreKnown) }} der 2.000 häufigsten</p>
      </div>
      <div>
        <p class="k-eyebrow">Satz-Check</p>
        <p class="m-0" style="font-size: 32px; font-weight: 800">{{ result.satzcheck ? result.satzcheck.coverage + ' %' : '—' }}</p>
        <p v-if="result.satzcheck" class="k-small m-0">{{ result.satzcheck.verdict.title }}</p>
      </div>
      <div>
        <p class="k-eyebrow">Startpunkt</p>
        <p class="m-0" style="font-size: 32px; font-weight: 800">≈ {{ formatNumber(result.startHours) }} h</p>
        <p class="k-small m-0">von ≈ 1.150 h bis B2 (grobe Schätzung)</p>
      </div>
    </section>
    <section class="k-card">
      <h2 class="k-h2">Fähigkeiten (grob)</h2>
      <ul class="list-none m-0 mt-3 p-0">
        <li v-for="s in skills" :key="s.key" class="flex justify-between gap-3 py-3" style="border-top: 1px solid var(--surface-2)">
          <span>{{ s.label }}<span v-if="result.notes[s.key]" class="k-hint block">{{ result.notes[s.key] }}</span></span>
          <strong style="font-size: 20px">{{ result.skills[s.key] || '—' }}</strong>
        </li>
      </ul>
    </section>
  </div>
</template>
