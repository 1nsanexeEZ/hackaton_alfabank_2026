<script setup lang="ts">
import { computed } from 'vue'

import { ColumnChart } from '@/shared/ui'

import { toAmount, useBoard } from '../../model/useBoardData'

const { overview } = useBoard()

/** Подпись диапазона из границ сводки, ₽: «до 1 млн», «1–3 млн», «30+ млн» */
function bucketLabel(min: string, max: string | null) {
  const from = toAmount(min) / 1_000_000
  if (max === null) return `${from}+ млн`
  const to = toAmount(max) / 1_000_000
  return from ? `${from}–${to} млн` : `до ${to} млн`
}

const buckets = computed(() => overview.value?.amount_buckets ?? [])
</script>

<template>
  <ColumnChart
    :labels="buckets.map((bucket) => bucketLabel(bucket.min, bucket.max))"
    :series="[{ label: 'Заявок в диапазоне', color: 'var(--color-night)', values: buckets.map((bucket) => bucket.count) }]"
    :height="148"
  />
</template>
