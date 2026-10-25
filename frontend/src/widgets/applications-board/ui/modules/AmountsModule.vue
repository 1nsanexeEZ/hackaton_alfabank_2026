<script setup lang="ts">
import { computed } from 'vue'

import { ColumnChart } from '@/shared/ui'

import { amountOf, useBoard } from '../../model/useBoardData'

const { applications } = useBoard()

/** Диапазоны сумм, ₽: верхняя граница не включается */
const BUCKETS: readonly { label: string; to: number }[] = [
  { label: 'до 1 млн', to: 1_000_000 },
  { label: '1–3 млн', to: 3_000_000 },
  { label: '3–10 млн', to: 10_000_000 },
  { label: '10–30 млн', to: 30_000_000 },
  { label: '30+ млн', to: Infinity },
]

const counts = computed(() => {
  const withAmount = applications.value.map(amountOf).filter((amount) => amount > 0)
  return BUCKETS.map((bucket, index) => {
    const from = index ? BUCKETS[index - 1]!.to : 0
    return withAmount.filter((amount) => amount >= from && amount < bucket.to).length
  })
})
</script>

<template>
  <ColumnChart
    :labels="BUCKETS.map((bucket) => bucket.label)"
    :series="[{ label: 'Заявок в диапазоне', color: 'var(--color-night)', values: counts }]"
    :height="148"
  />
</template>
