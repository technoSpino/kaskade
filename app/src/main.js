import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import '@fontsource/archivo/400.css'
import '@fontsource/archivo/500.css'
import '@fontsource/archivo/600.css'
import '@fontsource/archivo/700.css'
import '@fontsource/archivo/800.css'
import '@fontsource/archivo-black/400.css'
import '@fontsource/literata/400.css'
import '@fontsource/literata/500.css'
import '@fontsource/literata/600.css'
import '@fontsource/source-serif-4/400.css'
import './styles/digits.css'
import '@fontsource/source-serif-4/600.css'
import '@fontsource/source-serif-4/700.css'
import '@fontsource/atkinson-hyperlegible/400.css'
import '@fontsource/atkinson-hyperlegible/700.css'
import '@fontsource/libre-franklin/400.css'
import '@fontsource/libre-franklin/600.css'
import '@fontsource/libre-franklin/700.css'
import './style.css'
import App from './App.vue'
import { applyTheme, resolveTheme, storedTheme, systemTheme } from './lib/theme'
import { unlockOnFirstGesture } from './lib/speech'

// Apply the theme before the first paint (the server setting may refine it later).
applyTheme(resolveTheme({ local: storedTheme(), server: null, system: systemTheme() }))

// #28: Karten plays each card's audio by itself; Safari allows that once a click has unlocked the player.
unlockOnFirstGesture()

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.mount('#app')
