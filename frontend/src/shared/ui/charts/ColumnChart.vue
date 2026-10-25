<script setup lang="ts">
import { computed } from 'vue'

import type { ChartSeries } from './types'

/**
 * Столбики с накоплением: по столбику на подпись оси, ряды складываются снизу вверх.
 * Подписи оси показываем не все, если их много, — каждую n-ю, чтобы не налезали.
 */
const props = withDefaults(defineProps<{ labels: string[]; series: ChartSeries[]; height?: number }>(), { height: 176 })

const totals = computed(() => props.labels.map((_, index) => props.series.reduce((sum, row) => sum + (row.values[index] ?? 0), 0)))
const max = computed(() => Math.max(1, ...totals.value))
const labelStep = computed(() => Math.max(1, Math.ceil(props.labels.length / 10)))

/** Подсказка по столбику: дата и значение каждого ряда */
const titleOf = (index: number) =>
  [props.labels[index], ...props.series.map((row) => `${row.label}: ${row.values[index] ?? 0}`)].join('\n')
</script>

<template>
  <div>
    <div class="flex items-end gap-1" :style="{ height: `${height}px` }" role="img" :aria-label="`Столбчатая диаграмма: ${series.map((row) => row.label).join(', ')}`">
      <div
        v-for="(label, index) in labels"
        :key="label"
        class="group flex h-full min-w-0 flex-1 flex-col justify-end"
        :title="titleOf(index)"
      >
        <span v-if="totals[index]" class="mb-1 text-center text-[10px] text-ink-secondary opacity-0 transition-opacity group-hover:opacity-100">{{ totals[index] }}</span>
        <div class="column flex flex-col-reverse overflow-hidden rounded-md bg-surface" :style="{ height: totals[index] ? `${(totals[index]! / max) * 100}%` : '3px' }">
          <div v-for="row in series" :key="row.label" :style="{ flexGrow: row.values[index] ?? 0, background: row.color }" />
        </div>
      </div>
    </div>
    <div class="mt-2 flex gap-1 text-[10px] text-ink-secondary">
      <span v-for="(label, index) in labels" :key="label" class="min-w-0 flex-1 truncate text-center">
        {{ index % labelStep === 0 ? label : '' }}
      </span>
    </div>
    <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-secondary">
      <li v-for="row in series" :key="row.label" class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-sm" :style="{ background: row.color }" aria-hidden="true" />
        {{ row.label }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.column {
  transition: height 0.6s ease;
}

@media (prefers-reduced-motion: reduce) {
  .column {
    transition: none;
  }
}
</style>
