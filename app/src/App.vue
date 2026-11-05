<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import KaskadeHeader from './components/kaskade/KaskadeHeader.vue'
import { useStatusStore } from './stores/statusStore'

const route = useRoute()
// The original grammar pages ("Nachschlagen") keep their own light design.
const LEGACY = ['/nachschlagen', '/tables', '/modal-verbs', '/sentence-structure', '/verb-conjugation', '/past-tense', '/prepositions', '/werden', '/flashcards', '/exercises']
const legacy = computed(() => LEGACY.includes(route.path))
const status = useStatusStore()
</script>

<template>
  <div class="k-app">
    <KaskadeHeader />
    <div v-if="status.error" class="k-banner" role="alert" data-testid="server-banner">
      <span>{{ status.error }} Deine Daten sind sicher — die Seite funktioniert wieder, sobald der Dienst läuft.</span>
      <button class="k-btn k-btn-sm" @click="status.load()">Erneut versuchen</button>
    </div>
    <div :class="{ 'k-legacy': legacy }">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
  </div>
</template>

<style scoped>
.k-banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 10px 24px;
  background: var(--callout);
  color: var(--text);
  border-bottom: 3px solid var(--danger);
  font-size: 14px;
  font-weight: 600;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
