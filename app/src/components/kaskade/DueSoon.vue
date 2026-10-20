<script setup>
import { computed, ref } from 'vue'
import { api } from '../../lib/api'
import { bookLine, dayLabel, dueFor, dueLabel, withinDays } from '../../lib/materials'

// "Bald fällig" (#16 Update 6): purchases and other to-dos with a date, due date first.
// Shown from 14 days before the due date (overdue stays); the Fahrplan lists all of them.
const props = defineProps({ notices: { type: Array, default: () => [] }, today: { type: String, required: true } })
const emit = defineEmits(['changed'])
const error = ref(null)
const items = computed(() => props.notices.filter((n) => withinDays(n.by, props.today, 14)).map((n) => ({ ...n, due: dueLabel(n.by, props.today) })))

async function tick(n) {
  try {
    if (n.type === 'book') await api.post(`/books/${n.id}/bought`, { done: true })
    else await api.post(`/setup/${n.id}`, { done: true })
    emit('changed')
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <section v-if="items.length" class="k-card" aria-labelledby="due-h" data-testid="due-soon">
    <h2 id="due-h" class="k-h2">Bald fällig</h2>
    <p v-if="error" class="k-error m-0 mt-2" role="alert">{{ error }}</p>
    <ul class="list-none m-0 mt-2 p-0">
      <li v-for="n in items" :key="n.id" class="ds-row" :data-testid="`due-${n.id}`" :data-overdue="n.due.overdue">
        <div class="min-w-0">
          <p :class="['ds-date', { 'ds-overdue': n.due.overdue }]">{{ n.due.text }}</p>
          <p class="m-0" style="font-weight: 700">{{ n.type === 'book' ? `${n.title} kaufen` : n.title }}</p>
          <p class="k-small m-0 mt-0.5">
            {{ dueFor(n) }}<template v-if="n.type === 'book'"> · {{ bookLine(n.book, ', ') }}<template v-if="n.byEbook"> · E-Book reicht bis {{ dayLabel(n.byEbook) }} ({{ n.book.ebook.price }})</template></template>
          </p>
          <p v-if="n.mode" class="k-small m-0 mt-0.5" style="color: var(--text)" :data-testid="`due-mode-${n.id}`">Verschoben: {{ n.mode.why }}</p>
          <p v-if="n.type === 'book'" class="k-small m-0 mt-0.5 flex flex-wrap gap-x-3">
            <a v-for="s in n.book.shops" :key="s.url" :href="s.url" target="_blank" rel="noopener">{{ s.name }} ↗</a>
          </p>
          <p v-else class="k-small m-0 mt-0.5">{{ n.text }} <a v-if="n.url" :href="n.url" target="_blank" rel="noopener">Zur Seite ↗</a></p>
        </div>
        <button class="k-btn k-btn-ghost k-btn-sm" style="flex: none" :data-testid="`due-done-${n.id}`" @click="tick(n)">{{ n.type === 'book' ? '✓ gekauft' : '✓ erledigt' }}</button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.ds-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 12px 0;
  border-top: 1px solid var(--surface-2);
}
.ds-row > div { flex: 1 1 320px; }
.ds-date { margin: 0 0 2px; font-size: 15px; font-weight: 800; color: var(--text); }
.ds-row[data-overdue='true'] { border-left: 4px solid var(--danger); padding-left: 12px; }
.ds-overdue { color: var(--text); }
</style>
