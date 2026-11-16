<script setup>
import { formatNumber } from '../../lib/format'

defineProps({ result: { type: Object, required: true } })

const bandLabel = (b) => `${formatNumber(b.from)}–${formatNumber(b.to)}`
</script>

<template>
  <section class="k-card k-card-strong flex flex-col gap-4" aria-labelledby="vr-h" data-testid="vocab-result">
    <h2 id="vr-h" class="k-eyebrow">Wortschatz · Ergebnis</h2>
    <div class="flex flex-wrap gap-8">
      <div>
        <p class="m-0" style="font-size: 44px; font-weight: 800">≈ {{ formatNumber(result.estimate) }}</p>
        <p class="k-small m-0">Wörter bekannt (gemessen bis Rang 8.000)</p>
      </div>
      <div>
        <p class="m-0" style="font-size: 44px; font-weight: 800">{{ Math.round(result.coreShare * 100) }} %</p>
        <p class="k-small m-0">der 2.000 häufigsten Wörter (≈ {{ formatNumber(result.coreKnown) }})</p>
      </div>
    </div>
    <ul class="list-none m-0 p-0 flex flex-col gap-2">
      <li v-for="b in result.bands" :key="b.id" class="grid items-center gap-3" style="grid-template-columns: 92px minmax(0, 1fr) 48px">
        <span class="k-hint">{{ bandLabel(b) }}</span>
        <div class="k-progress" style="height: 12px" :title="`${Math.round(b.corrected * 100)} % bekannt`">
          <div :style="{ width: Math.round(b.corrected * 100) + '%' }"></div>
        </div>
        <strong class="text-right" style="font-size: 14px">{{ Math.round(b.corrected * 100) }} %</strong>
      </li>
    </ul>
    <p class="k-hint m-0">Fantasiewörter mit Ja: {{ Math.round(result.falseAlarmRate * 100) }} % — wird abgezogen.</p>
    <p v-if="!result.reliable" class="k-callout m-0" role="note">
      <strong>Achtung:</strong> Du hast viele erfundene Wörter erkannt. Das Ergebnis ist deshalb unsicher — mach den Test gern noch einmal und sag nur Ja, wenn du die Bedeutung wirklich kennst.
    </p>
  </section>
</template>
