<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../../lib/api'
import { formatClock } from '../../lib/format'
import OriginBadge from './OriginBadge.vue'
import { useStatusStore } from '../../stores/statusStore'

// Record short spoken answers with MediaRecorder and upload them. No grading yet.
const props = defineProps({
  questions: { type: Array, required: true },
  context: { type: String, required: true },
  state: { type: Object, default: null }
})
const emit = defineEmits(['progress', 'done'])

const recordings = ref(props.state?.recordings ?? props.questions.map(() => null))
const index = ref(Math.max(0, recordings.value.indexOf(null)))
const recording = ref(false)
const seconds = ref(0)
const error = ref(null)
const uploading = ref(false)
let recorder = null
let stream = null
let chunks = []
let tick = 0

const q = computed(() => props.questions[index.value])
const supported = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'
// Browsers only allow the microphone over HTTPS (#17): point to Kaskade's HTTPS address, same page.
const insecure = typeof window !== 'undefined' && !window.isSecureContext
const status = useStatusStore()
const httpsHere = computed(() => (status.httpsUrl ? `${status.httpsUrl}${window.location.pathname}${window.location.search}` : null))
const allDone = computed(() => recordings.value.every((r) => r))

async function start() {
  error.value = null
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    error.value = 'Kein Zugriff auf das Mikrofon. Bitte im Browser erlauben — oder diesen Teil überspringen.'
    return
  }
  chunks = []
  recorder = new MediaRecorder(stream)
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  recorder.onstop = upload
  recorder.start()
  recording.value = true
  seconds.value = 0
  tick = setInterval(() => {
    seconds.value++
    if (seconds.value >= (q.value.seconds || 90) + 30) stop()
  }, 1000)
}

function stop() {
  clearInterval(tick)
  if (recorder && recorder.state !== 'inactive') recorder.stop()
  stream?.getTracks().forEach((t) => t.stop())
  recording.value = false
}

async function upload() {
  const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
  const form = new FormData()
  form.append('audio', blob, 'antwort.webm')
  form.append('context', `${props.context}:${q.value.id}`)
  uploading.value = true
  try {
    const r = await api.post('/recordings', form)
    const next = recordings.value.slice()
    next[index.value] = r.id
    recordings.value = next
    emit('progress', { recordings: next })
    if (index.value < props.questions.length - 1) index.value++
  } catch (e) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}

function finish(skipped = false) {
  stop()
  emit('done', { recordings: recordings.value, skipped })
}

onBeforeUnmount(stop)
</script>

<template>
  <section class="k-card flex flex-col gap-4" aria-labelledby="sp-h" data-testid="speaking-task">
    <p class="k-eyebrow flex flex-wrap items-center gap-x-3 gap-y-1">Frage {{ index + 1 }} von {{ questions.length }} <OriginBadge v-if="q.origin" :origin="q.origin" :source="q.source" /></p>
    <h2 id="sp-h" class="k-read m-0" style="font-size: 24px; font-weight: 600; line-height: 1.35">{{ q.prompt }}</h2>
    <p class="k-hint m-0">{{ q.hint }}</p>
    <p v-if="insecure" class="k-error m-0" data-testid="sp-https">
      Aufnahmen gehen nur über die HTTPS-Adresse<template v-if="httpsHere">: <a :href="httpsHere">{{ status.httpsUrl }}</a> — dort diese Seite öffnen</template>. Du kannst diesen Teil auch überspringen.
    </p>
    <p v-else-if="!supported" class="k-error m-0">Dieser Browser kann keine Aufnahmen machen. Du kannst diesen Teil überspringen.</p>
    <p v-if="error" class="k-error m-0" role="alert">{{ error }}</p>

    <div class="flex flex-wrap items-center gap-3">
      <button v-if="!recording" class="k-btn" :disabled="!supported || uploading" data-testid="sp-record" @click="start">
        ● {{ recordings[index] ? 'Neu aufnehmen' : 'Aufnahme starten' }}
      </button>
      <button v-else class="k-btn" data-testid="sp-stop" @click="stop">■ Stopp · {{ formatClock(seconds) }}</button>
      <audio v-if="recordings[index] && !recording" :src="`/api/recordings/${recordings[index]}/file`" controls preload="none"></audio>
      <span v-if="uploading" class="k-small">Speichert …</span>
    </div>

    <ol class="list-none m-0 p-0 flex flex-wrap gap-2">
      <li v-for="(qq, i) in questions" :key="qq.id">
        <button
          type="button"
          class="k-btn k-btn-ghost k-btn-sm"
          :aria-current="i === index ? 'step' : undefined"
          :disabled="recording"
          @click="index = i"
        >{{ i + 1 }} {{ recordings[i] ? '✓' : '' }}</button>
      </li>
    </ol>

    <div class="flex flex-wrap gap-3 justify-between">
      <button class="k-btn k-btn-ghost k-btn-sm" :disabled="recording" data-testid="sp-skip" @click="finish(true)">Überspringen</button>
      <button class="k-btn" :disabled="!allDone || recording" data-testid="sp-done" @click="finish(false)">Fertig</button>
    </div>
  </section>
</template>
