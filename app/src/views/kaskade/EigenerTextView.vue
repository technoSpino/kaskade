<script setup>
import { ref } from 'vue'
import { api } from '../../lib/api'
import AnalyzedText from '../../components/kaskade/AnalyzedText.vue'
import WordPanel from '../../components/kaskade/WordPanel.vue'
import CaseLegend from '../../components/kaskade/CaseLegend.vue'

const text = ref('')
const analysis = ref(null)
const token = ref(null)
const lens = ref(true)
const busy = ref(false)
const error = ref(null)

async function run() {
  busy.value = true
  error.value = null
  token.value = null
  try {
    analysis.value = await api.post('/analyze', { text: text.value })
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="k-main" data-testid="eigener-text">
    <div>
      <p class="k-eyebrow mb-1.5"><router-link to="/lesen">Lesen</router-link></p>
      <h1 class="k-h1">Eigener Text</h1>
      <p class="k-lead">Füge einen deutschen Text ein — einen Artikel, eine Nachricht, einen Absatz aus einem Buch. Kaskade zeigt neue Wörter und mit der Kasus-Linse die Fälle. Der Text wird nicht gespeichert, nur gemined Sätze.</p>
    </div>
    <section v-if="!analysis" class="k-card flex flex-col gap-3">
      <textarea v-model="text" class="k-input" aria-label="Text" placeholder="Text hier einfügen …" data-testid="paste-text"></textarea>
      <div><button class="k-btn" :disabled="!text.trim() || busy" data-testid="paste-run" @click="run">{{ busy ? 'Analysiert …' : 'Lesen' }}</button></div>
      <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>
    </section>
    <template v-else>
      <div class="flex flex-wrap gap-2 items-center">
        <button class="k-btn k-btn-ghost k-btn-sm" @click="analysis = null">Anderer Text</button>
        <button class="k-btn k-btn-ghost k-btn-sm" :aria-pressed="lens" @click="lens = !lens">Kasus-Linse {{ lens ? 'aus' : 'an' }}</button>
      </div>
      <CaseLegend v-if="lens" />
      <div class="flex flex-wrap gap-6 items-start">
        <article class="k-card min-w-0" style="flex: 999 1 560px">
          <AnalyzedText :analysis="analysis" :lens="lens" :selected="token?.i ?? null" @select="token = $event" />
        </article>
        <aside class="min-w-0" style="flex: 1 1 300px; position: sticky; top: 12px">
          <WordPanel :analysis="analysis" :token="token" source="Eigener Text" />
        </aside>
      </div>
    </template>
  </main>
</template>
