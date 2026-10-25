<script setup lang="ts">
import { computed } from 'vue'

import { DonutChart } from '@/shared/ui'

import { useBoard } from '../../model/useBoardData'

const { metrics } = useBoard()

const totals = computed(() =>
  (metrics.value?.rows ?? []).reduce(
    (sum, row) => ({ auto: sum.auto + row.auto_decisions, manual: sum.manual + row.manual_reviews }),
    { auto: 0, manual: 0 },
  ),
)
const segments = computed(() => [
  { label: 'Решила автоматика', value: totals.value.auto, color: 'var(--color-night)' },
  { label: 'Передали специалисту', value: totals.value.manual, color: 'var(--color-brand)' },
])
const autoShare = computed(() => {
  const all = totals.value.auto + totals.value.manual
  return all ? `${Math.round((totals.value.auto / all) * 100)}%` : '—'
})
</script>

<template>
  <DonutChart :segments="segments" :center-value="autoShare" center-label="сразу автоматикой" />
</template>
