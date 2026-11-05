<template>
  <p class="cl m-0" aria-label="Kasus-Linse: Farben">
    <span class="cl-n">N Nominativ</span><span class="cl-a">A Akkusativ</span><span class="cl-d">D Dativ</span><span class="cl-g">G Genitiv</span>
    <span class="k-hint">· automatisch erkannt, kann sich irren</span>
  </p>
</template>

<style scoped>
.cl { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; font-weight: 700; }
.cl-n { color: var(--case-n); }
.cl-a { color: var(--case-a); }
.cl-d { color: var(--case-d); }
.cl-g { color: var(--case-g); }
</style>
