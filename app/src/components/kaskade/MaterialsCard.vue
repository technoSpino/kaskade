<script setup>
import { computed } from 'vue'
import { groupTitle, itemLine, STATUS_LABEL, withSecureCheck } from '../../lib/materials'
import OriginBadge from './OriginBadge.vue'

// "Material für heute und morgen" (#16): only what today's and the next plan day's blocks use,
// "✓ bereit" or "→ zu tun". Purchases and other dated to-dos live in "Bald fällig" (DueSoon).
const props = defineProps({ blocks: { type: Array, default: () => [] }, data: { type: Object, default: null } })
const secure = typeof window !== 'undefined' && window.isSecureContext

const blockLabel = (id) => {
  const b = props.blocks.find((x) => x.id === id)
  return b?.label ?? b?.title ?? id
}
// #27: a block's second item ("then") gets its own line, right after the first
const groups = computed(() =>
  props.data
    ? [props.data.today, props.data.next].map((g) => ({
        ...g,
        items: g.items.flatMap((it) => [it, ...(it.then ?? []).map((n, i) => ({ ...n, then: undefined, key: `${it.block}-${i + 1}`, after: true }))])
          .map((it) => withSecureCheck({ key: it.block, ...it }, secure, props.data.httpsUrl))
      }))
    : []
)
</script>

<template>
  <section class="k-card" aria-labelledby="mat-h" data-testid="materials">
    <h2 id="mat-h" class="k-h2">Material für heute und morgen</h2>
    <div v-for="g in groups" :key="g.kind" class="mt-group" :data-testid="`mat-${g.kind}`">
      <h3 class="mt-day">{{ groupTitle(g) }}</h3>
      <p v-if="!g.planDay" class="k-small m-0">Kein Lernblock.</p>
      <ul v-else class="list-none m-0 p-0">
        <li v-for="it in g.items" :key="it.key" class="mt-row" :data-testid="`mat-${g.kind}-${it.key}`" :data-status="it.status">
          <div class="min-w-0">
            <p class="mt-block">{{ blockLabel(it.block) }}{{ it.after ? ' · danach' : '' }}</p>
            <p class="m-0" style="font-weight: 700">{{ itemLine(it) }}</p>
            <p class="k-small m-0 mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <OriginBadge :origin="it.origin" :source="it.source" />
              <span v-if="it.detail">{{ it.detail }}</span>
            </p>
            <p v-if="it.mode?.why" class="k-small m-0 mt-0.5" style="color: var(--text); font-weight: 600">{{ it.mode.why }}</p>
          </div>
          <div class="flex flex-col items-end gap-1">
            <span :class="['k-chip', it.status === 'ready' ? 'k-chip-success' : 'mt-todo']">{{ STATUS_LABEL[it.status] }}</span>
            <a v-if="it.fix" :href="it.fix.href" class="k-small" style="font-weight: 600">{{ it.fix.label }} →</a>
          </div>
        </li>
      </ul>
    </div>
    <p v-if="data?.check?.gaps?.length" class="k-hint m-0 mt-3" data-testid="mat-gaps">
      Materialcheck: {{ data.check.gaps.length }} {{ data.check.gaps.length === 1 ? 'Lücke' : 'Lücken' }} in den nächsten 7 Tagen — Kaskade füllt sie beim nächsten Abgleich.
    </p>
  </section>
</template>

<style scoped>
.mt-group { margin-top: 18px; }
.mt-day { margin: 0 0 4px; font-size: 15px; font-weight: 800; color: var(--text); }
.mt-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  padding: 10px 0;
  border-top: 1px solid var(--surface-2);
}
.mt-block { margin: 0; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.mt-todo { background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong); }
</style>
