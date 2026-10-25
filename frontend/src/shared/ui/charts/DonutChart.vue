<script setup lang="ts">
import { computed } from 'vue'

import type { ChartSegment } from './types'

/**
 * Кольцевая диаграмма с легендой: доли сегментов, в центре — итог или главная цифра.
 * Цвета — CSS-значения (например, var(--color-success)), чтобы диаграмма жила в той же палитре.
 */
const props = withDefaults(
  defineProps<{
    segments: ChartSegment[]
    /** Крупная цифра в центре; по умолчанию — сумма сегментов */
    centerValue?: string
    centerLabel?: string
    formatValue?: (value: number) => string
  }>(),
  { centerValue: undefined, centerLabel: undefined, formatValue: (value: number) => String(value) },
)

const RADIUS = 42
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

const total = computed(() => props.segments.reduce((sum, item) => sum + Math.max(item.value, 0), 0))

/** Дуги по порядку: длина — доля, сдвиг — сумма предыдущих */
const arcs = computed(() => {
  let offset = 0
  return props.segments
    .filter((item) => item.value > 0)
    .map((item) => {
      const length = total.value ? (item.value / total.value) * CIRCUMFERENCE : 0
      const arc = { ...item, dash: `${length} ${CIRCUMFERENCE - length}`, offset: -offset }
      offset += length
      return arc
    })
})

const share = (value: number) => (total.value ? Math.round((value / total.value) * 100) : 0)
</script>

<template>
  <!-- В узкой карточке легенда уходит под кольцо, в широкой — встаёт справа -->
  <div class="@container">
  <div class="flex flex-col items-center gap-5 @sm:flex-row">
    <div class="relative size-36 shrink-0">
      <svg viewBox="0 0 100 100" class="size-full -rotate-90" role="img" :aria-label="segments.map((item) => `${item.label}: ${formatValue(item.value)}`).join(', ')">
        <circle cx="50" cy="50" :r="RADIUS" fill="none" stroke="var(--color-surface)" stroke-width="12" />
        <circle
          v-for="arc in arcs"
          :key="arc.label"
          cx="50"
          cy="50"
          :r="RADIUS"
          fill="none"
          :stroke="arc.color"
          stroke-width="12"
          :stroke-dasharray="arc.dash"
          :stroke-dashoffset="arc.offset"
          class="donut__arc"
        />
      </svg>
      <div class="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span class="text-2xl font-bold text-ink">{{ centerValue ?? formatValue(total) }}</span>
        <span v-if="centerLabel" class="max-w-20 text-[11px] leading-tight text-ink-secondary">{{ centerLabel }}</span>
      </div>
    </div>
    <ul class="w-full flex-1 space-y-2 text-sm">
      <li v-for="item in segments" :key="item.label" class="flex items-center gap-2">
        <span class="size-2.5 shrink-0 rounded-full" :style="{ background: item.color }" aria-hidden="true" />
        <span class="min-w-0 flex-1 truncate text-ink-secondary">{{ item.label }}</span>
        <span class="font-semibold text-ink tabular-nums">{{ formatValue(item.value) }}</span>
        <span class="w-9 text-right text-xs text-ink-secondary tabular-nums">{{ share(item.value) }}%</span>
      </li>
    </ul>
  </div>
  </div>
</template>

<style scoped>
.donut__arc {
  transition:
    stroke-dasharray 0.6s ease,
    stroke-dashoffset 0.6s ease;
}

@media (prefers-reduced-motion: reduce) {
  .donut__arc {
    transition: none;
  }
}
</style>
