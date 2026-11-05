<script setup>
import { ref } from 'vue'
import VocabTest from '../../components/kaskade/VocabTest.vue'
import VocabResult from '../../components/kaskade/VocabResult.vue'

const result = ref(null)
const run = ref(0)

function again() {
  result.value = null
  run.value++
}
</script>

<template>
  <main class="k-main">
    <div>
      <p class="k-eyebrow mb-1.5">Einzeltest</p>
      <h1 class="k-h1">Wortschatz-Test</h1>
      <p class="k-lead">Wie viele der häufigsten deutschen Wörter kennst du? Ergebnis in etwa 5 Minuten — auch Teil der Einstufung.</p>
    </div>
    <VocabResult v-if="result" :result="result" />
    <div v-if="result">
      <button class="k-btn k-btn-ghost" @click="again">Noch einmal testen</button>
    </div>
    <VocabTest v-else :key="run" @done="result = $event" />
  </main>
</template>
