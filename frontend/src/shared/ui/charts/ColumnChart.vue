<script setup lang="ts">
import { computed } from 'vue'

import type { ChartSeries } from './types'

/**
 * Столбики с накоплением: по столбику на подпись оси, ряды складываются снизу вверх.
 * Подписи оси показываем не все, если их много, — каждую n-ю, чтобы не налезали.
 *
 * Шкала с запасом и сеткой: одна заявка за месяц — четверть высоты, а не столбик во весь график.
 * Столбик не шире 1.75rem: на 7 днях они не расплываются в плиты.
 */
const props = withDefaults(defineProps<{ labels: string[]; series: ChartSeries[]; height?: number }>(), { height: 176 })

const totals = computed(() => props.labels.map((_, index) => props.series.reduce((sum, row) => sum + (row.values[index] ?? 0), 0)))

/** Верх шкалы — ближайшее «круглое» значение не меньше 4, у которого половина — целое: 4, 10, 20, 40, 100… */
const scale = computed(() => {
  const max = Math.max(...totals.value, 0)
  for (let power = 1; ; power *= 10) {
    const nice = [4 * power, 10 * power, 20 * power].find((value) => value >= max)
    if (nice) return nice
  }
})
const ticks = computed(() => [0, scale.value / 2, scale.value])
const labelStep = computed(() => Math.max(1, Math.ceil(props.labels.length / 10)))

/** Подсказка по столбику: дата и значение каждого ряда */
const titleOf = (index: number) =>
  [props.labels[index], ...props.series.map((row) => `${row.label}: ${row.values[index] ?? 0}`)].join('\n')
</script>

<template>
  <div>
    <div class="relative pl-7" :style="{ height: `${height}px` }">
      <template v-for="tick in ticks" :key="tick">
        <span
          class="pointer-events-none absolute right-0 left-7 border-t border-dashed border-line"
          :style="{ bottom: `${(tick / scale) * 100}%` }"
          aria-hidden="true"
        />
        <span
          class="absolute left-0 w-5 translate-y-1/2 text-right text-[10px] text-ink-muted tabular-nums"
          :style="{ bottom: `${(tick / scale) * 100}%` }"
          aria-hidden="true"
        >
          {{ tick }}
        </span>
      </template>
      <div class="relative flex h-full items-end gap-1" role="img" :aria-label="`Столбчатая диаграмма: ${series.map((row) => row.label).join(', ')}`">
        <div
          v-for="(label, index) in labels"
          :key="label"
          class="group flex h-full min-w-0 flex-1 flex-col items-center justify-end"
          :title="titleOf(index)"
        >
          <span v-if="totals[index]" class="mb-1 text-center text-[10px] text-ink-secondary opacity-0 transition-opacity group-hover:opacity-100">{{ totals[index] }}</span>
          <div
            class="column flex w-full max-w-7 flex-col-reverse overflow-hidden rounded-md"
            :class="totals[index] ? 'bg-surface' : 'bg-surface-strong/60'"
            :style="{ height: totals[index] ? `${(totals[index]! / scale) * 100}%` : '2px' }"
          >
            <div v-for="row in series" :key="row.label" :style="{ flexGrow: row.values[index] ?? 0, background: row.color }" />
          </div>
        </div>
      </div>
    </div>
    <div class="mt-2 flex gap-1 pl-7 text-[10px] text-ink-secondary">
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
