<script setup lang="ts">
import { computed } from 'vue'

import { ColumnChart, type ChartSeries } from '@/shared/ui'

import { useBoard } from '../../model/useBoardData'

const { metrics, days } = useBoard()

/** Метрики приходят строками «день × продукт» — складываем по дням, пустые дни — нули */
const byDay = computed(() => {
  const totals = new Map<string, { submitted: number; approved: number; counter: number; rejected: number }>()
  for (const row of metrics.value?.rows ?? []) {
    const day = totals.get(row.day) ?? { submitted: 0, approved: 0, counter: 0, rejected: 0 }
    day.submitted += row.submitted
    day.approved += row.approved
    day.counter += row.counter_offers
    day.rejected += row.rejected
    totals.set(row.day, day)
  }
  return days.value.map((day) => totals.get(day) ?? { submitted: 0, approved: 0, counter: 0, rejected: 0 })
})

// Подпись — только число: месяц понятен по периоду, а «25.10» не помещается под узким столбиком
const labels = computed(() => days.value.map((day) => String(Number(day.slice(8, 10)))))
const series = computed<ChartSeries[]>(() => [
  { label: 'Одобрено', color: 'var(--color-success)', values: byDay.value.map((day) => day.approved) },
  { label: 'Встречное предложение', color: 'var(--color-signal-warn)', values: byDay.value.map((day) => day.counter) },
  { label: 'Отказ', color: 'var(--color-brand)', values: byDay.value.map((day) => day.rejected) },
])
const submitted = computed(() => byDay.value.reduce((sum, day) => sum + day.submitted, 0))
const decided = computed(() => byDay.value.reduce((sum, day) => sum + day.approved + day.counter + day.rejected, 0))
</script>

<template>
  <div>
    <p class="mb-4 text-sm text-ink-secondary">
      Подано за период: <b class="font-semibold text-ink">{{ submitted }}</b> · решений: <b class="font-semibold text-ink">{{ decided }}</b>
    </p>
    <ColumnChart :labels="labels" :series="series" />
  </div>
</template>
