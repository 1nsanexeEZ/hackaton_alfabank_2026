<script setup lang="ts">
import { computed } from 'vue'

import type { ChartSegment } from './types'

/** Горизонтальные полосы: подпись, значение и полоса длиной в долю от самой большой строки */
const props = withDefaults(defineProps<{ items: ChartSegment[]; formatValue?: (value: number) => string }>(), {
  formatValue: (value: number) => String(value),
})

const max = computed(() => Math.max(1, ...props.items.map((item) => item.value)))
</script>

<template>
  <ul class="space-y-3">
    <li v-for="item in items" :key="item.label">
      <div class="flex items-baseline justify-between gap-3 text-sm">
        <span class="min-w-0 truncate text-ink">{{ item.label }}</span>
        <span class="shrink-0 font-semibold text-ink tabular-nums">{{ formatValue(item.value) }}</span>
      </div>
      <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-surface">
        <div class="bar h-full rounded-full" :style="{ width: `${(item.value / max) * 100}%`, background: item.color }" />
      </div>
      <p v-if="item.hint" class="mt-1 text-xs text-ink-secondary">{{ item.hint }}</p>
    </li>
  </ul>
</template>

<style scoped>
.bar {
  transition: width 0.6s ease;
}

@media (prefers-reduced-motion: reduce) {
  .bar {
    transition: none;
  }
}
</style>
