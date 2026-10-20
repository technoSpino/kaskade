import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import TablesView from '../views/TablesView.vue'
import FlashcardsView from '../views/FlashcardsView.vue'
import ModalVerbsView from '../views/ModalVerbsView.vue'
import SentenceStructureView from '../views/SentenceStructureView.vue'
import VerbConjugationView from '../views/VerbConjugationView.vue'
import PastTenseView from '../views/PastTenseView.vue'
import PrepositionsView from '../views/PrepositionsView.vue'
import WerdenView from '../views/WerdenView.vue'
import ExercisesView from '../views/ExercisesView.vue'

import HeuteView from '../views/kaskade/HeuteView.vue'

const routes = [
  // Kaskade
  { path: '/', name: 'Heute', component: HeuteView, meta: { title: 'Heute' } },
  { path: '/heute', redirect: '/' },
  {
    path: '/wortschatz',
    name: 'Wortschatz',
    component: () => import('../views/kaskade/WortschatzView.vue'),
    meta: { title: 'Wortschatz-Test' }
  },
  {
    path: '/schauen/:id?',
    name: 'Schauen',
    component: () => import('../views/kaskade/SchauenView.vue'),
    meta: { title: 'Schauen & minen' }
  },
  {
    path: '/satz-check',
    name: 'SatzCheck',
    component: () => import('../views/kaskade/SatzCheckView.vue'),
    meta: { title: 'Satz-Check' }
  },
  {
    path: '/einstufung',
    name: 'Einstufung',
    component: () => import('../views/kaskade/EinstufungView.vue'),
    meta: { title: 'Einstufung' }
  },
  {
    path: '/karten',
    name: 'Karten',
    component: () => import('../views/kaskade/KartenView.vue'),
    meta: { title: 'Karten' }
  },
  {
    path: '/aufgabe/:id',
    name: 'Aufgabe',
    component: () => import('../views/kaskade/AufgabeView.vue'),
    meta: { title: 'Prüfungsteil' }
  },
  {
    path: '/fahrplan',
    name: 'Fahrplan',
    component: () => import('../views/kaskade/FahrplanView.vue'),
    meta: { title: 'Fahrplan' }
  },
  {
    path: '/lesen',
    name: 'Lesen',
    component: () => import('../views/kaskade/LesenView.vue'),
    meta: { title: 'Lesen' }
  },
  {
    path: '/lesen/eigener-text',
    name: 'EigenerText',
    component: () => import('../views/kaskade/EigenerTextView.vue'),
    meta: { title: 'Eigener Text' }
  },
  {
    path: '/lesen/:id',
    name: 'Reader',
    component: () => import('../views/kaskade/ReaderView.vue'),
    meta: { title: 'Lesen' }
  },
  {
    path: '/pruefung',
    name: 'Pruefung',
    component: () => import('../views/kaskade/PruefungView.vue'),
    meta: { title: 'Prüfungstraining' }
  },
  {
    path: '/pruefung/:module(lesen|hoeren|schreiben)/:id',
    name: 'PruefungItem',
    component: () => import('../views/kaskade/PruefungItemView.vue'),
    meta: { title: 'Prüfungstraining' }
  },
  {
    path: '/immersion',
    name: 'Immersion',
    component: () => import('../views/kaskade/ImmersionView.vue'),
    meta: { title: 'Immersion' }
  },
  // Nachschlagen (the original grammar pages)
  {
    path: '/nachschlagen',
    name: 'Home',
    component: HomeView,
    meta: { title: 'Nachschlagen' }
  },
  {
    path: '/tables',
    name: 'Tables',
    component: TablesView,
    meta: { title: 'Declension Tables' }
  },
  {
    path: '/modal-verbs',
    name: 'ModalVerbs',
    component: ModalVerbsView,
    meta: { title: 'Modal Verbs' }
  },
  {
    path: '/sentence-structure',
    name: 'SentenceStructure',
    component: SentenceStructureView,
    meta: { title: 'Sentence Structure' }
  },
  {
    path: '/verb-conjugation',
    name: 'VerbConjugation',
    component: VerbConjugationView,
    meta: { title: 'Verb Conjugation' }
  },
  {
    path: '/past-tense',
    name: 'PastTense',
    component: PastTenseView,
    meta: { title: 'Past Tense (Perfekt)' }
  },
  {
    path: '/prepositions',
    name: 'Prepositions',
    component: PrepositionsView,
    meta: { title: 'Prepositions' }
  },
  {
    path: '/werden',
    name: 'Werden',
    component: WerdenView,
    meta: { title: 'Werden - Future Tense & Passive Voice' }
  },
  {
    path: '/flashcards',
    name: 'Flashcards',
    component: FlashcardsView,
    meta: { title: 'Practice Flashcards' }
  },
  {
    path: '/exercises',
    name: 'Exercises',
    component: ExercisesView,
    meta: { title: 'Skill Builder: Wo/Wohin, Prepositions, Nebensätze' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

// Update document title on route change
router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} · Kaskade` : 'Kaskade'
  next()
})

// After a deploy, a tab opened earlier still asks for the old lazy chunks, which are gone — the
// page didn't change and only the block timer started (#20). Load the target fresh instead
// (at most once in 10 s per target, so a real error can't loop).
const STALE_CHUNK = /dynamically imported module|Importing a module script failed|MIME type/i
router.onError((err, to) => {
  if (!STALE_CHUNK.test(err?.message ?? '') || !to) return
  const key = `kaskade-reload:${to.fullPath}`
  try {
    if (Date.now() - Number(sessionStorage.getItem(key) || 0) < 10000) return
    sessionStorage.setItem(key, String(Date.now()))
  } catch {
    /* private mode: reload anyway */
  }
  window.location.assign(to.fullPath)
})

export default router
