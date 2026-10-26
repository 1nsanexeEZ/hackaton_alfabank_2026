<script setup lang="ts">
import { computed } from 'vue'

import { formatMoneyShort, pluralize } from '@/shared/lib'
import { BarList } from '@/shared/ui'

import { toAmount, useBoard } from '../../model/useBoardData'

const { overview } = useBoard()

/** Бэкенд отдаёт продукты уже по убыванию числа заявок */
const items = computed(() =>
  (overview.value?.products ?? []).map((row, index) => ({
    label: row.product_name || row.product_code,
    value: row.count,
    hint: toAmount(row.amount) ? `запрошено ${formatMoneyShort(toAmount(row.amount))}` : undefined,
    color: index === 0 ? 'var(--color-brand)' : 'var(--color-night)',
  })),
)

const formatCount = (value: number) => `${value} ${pluralize(value, ['заявка', 'заявки', 'заявок'])}`
</script>

<template>
  <BarList :items="items" :format-value="formatCount" />
</template>
