<script setup lang="ts">
import { computed } from 'vue'

import { useProductCatalog } from '@/entities/credit-product'
import { formatMoneyShort, pluralize } from '@/shared/lib'
import { BarList } from '@/shared/ui'

import { amountOf, useBoard } from '../../model/useBoardData'

const { applications } = useBoard()
const { products } = useProductCatalog()

const items = computed(() => {
  const byCode = new Map<string, { count: number; sum: number }>()
  for (const item of applications.value) {
    const row = byCode.get(item.product_code) ?? { count: 0, sum: 0 }
    row.count++
    row.sum += amountOf(item)
    byCode.set(item.product_code, row)
  }
  return [...byCode.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .map(([code, row], index) => ({
      label: products.value?.find((product) => product.code === code)?.title ?? code,
      value: row.count,
      hint: row.sum ? `запрошено ${formatMoneyShort(row.sum)}` : undefined,
      color: index === 0 ? 'var(--color-brand)' : 'var(--color-night)',
    }))
})

const formatCount = (value: number) => `${value} ${pluralize(value, ['заявка', 'заявки', 'заявок'])}`
</script>

<template>
  <BarList :items="items" :format-value="formatCount" />
</template>
