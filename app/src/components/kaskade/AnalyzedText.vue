<script setup>
import { computed } from 'vue'
import { groupTokens } from '../../lib/reader'

// Renders analysed tokens: word states (neu/lernend) and the case lens
// (noun phrases underlined in the case colour, always with the letter N/A/D/G).
const props = defineProps({
  analysis: { type: Object, required: true },
  lens: { type: Boolean, default: true },
  states: { type: Boolean, default: true },
  selected: { type: Number, default: null }
})
const emit = defineEmits(['select'])

const lastOfChunk = computed(() => {
  const m = new Map()
  props.analysis.chunks.forEach((c, n) => m.set(c.end - 1, n))
  return m
})

function classes(t) {
  const out = []
  if (props.states && t.state === 'neu') out.push('at-neu')
  if (props.states && t.state === 'lernend') out.push('at-lernend')
  if (props.lens && t.chunk != null) out.push(`at-case at-case-${props.analysis.chunks[t.chunk].case}`)
  // #34: a separable verb is one word — tapping fällt or ein marks both (pair = the other half)
  if (props.selected != null && (props.selected === t.i || t.pair === props.selected)) out.push('at-selected')
  return out
}
const isWord = (t) => /\p{L}/u.test(t.text)
// Words with their punctuation and case letter never wrap apart (see groupTokens).
const groups = computed(() => groupTokens(props.analysis.tokens))
</script>

<template>
  <div class="k-read at-text" data-testid="analyzed-text"><template v-for="(g, gi) in groups" :key="gi"><span class="at-group"><template v-for="t in g" :key="t.i"><button
        v-if="isWord(t)"
        type="button"
        :class="['at-word', ...classes(t)]"
        :data-state="t.state || undefined"
        @click="emit('select', t)"
      >{{ t.text }}</button><span v-else :class="classes(t)">{{ t.text }}</span><sup
        v-if="lens && lastOfChunk.has(t.i)"
        :class="['at-sup', `at-sup-${analysis.chunks[lastOfChunk.get(t.i)].case}`]"
        :title="analysis.chunks[lastOfChunk.get(t.i)].explain"
      >{{ analysis.chunks[lastOfChunk.get(t.i)].case }}</sup></template></span>{{ g[g.length - 1].ws }}</template></div>
</template>

<style scoped>
.at-group { white-space: nowrap; }
.at-text { white-space: pre-wrap; font-size: clamp(19px, 2.4vw, 21px); line-height: 1.85; max-width: 66ch; }
.at-word {
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  padding: 0;
  margin: 0;
  cursor: pointer;
  border-radius: 3px;
}
.at-word:hover { background: var(--surface-2); }
.at-neu { background: var(--word-new-tint); box-shadow: inset 0 -2px 0 var(--word-new-underline); }
.at-lernend { text-decoration: underline 2px var(--word-learning); text-underline-offset: 5px; }
.at-case { border-bottom: 3px solid transparent; }
.at-case-N { border-bottom-color: var(--case-n); }
.at-case-A { border-bottom-color: var(--case-a); }
.at-case-D { border-bottom-color: var(--case-d); }
.at-case-G { border-bottom-color: var(--case-g); }
.at-selected { outline: 2px solid var(--focus); outline-offset: 1px; }
.at-sup { font-family: var(--font-ui); font-size: 10px; font-weight: 600; margin-left: 1px; }
.at-sup-N { color: var(--case-n); }
.at-sup-A { color: var(--case-a); }
.at-sup-D { color: var(--case-d); }
.at-sup-G { color: var(--case-g); }
</style>
