<script setup lang="ts">
import { computed } from 'vue'

import type { OfferDto } from '@/shared/api'
import { formatMoney, formatPercent, formatTerm } from '@/shared/lib'

/** Условия предложения крупными цифрами: сумма, ставка, платёж в месяц (тёмная плитка — главное), срок */
const props = defineProps<{ offer: OfferDto; compact?: boolean }>()

const tiles = computed(() => [
  { label: 'Сумма', value: formatMoney(Number(props.offer.amount)), main: false },
  { label: 'Ставка', value: formatPercent(Number(props.offer.rate)), main: false },
  { label: 'Платёж в месяц', value: formatMoney(Number(props.offer.monthly_payment)), main: true },
  { label: 'Срок', value: formatTerm(props.offer.term_months), main: false },
])
</script>

<template>
  <dl class="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
    <div
      v-for="tile in tiles"
      :key="tile.label"
      class="flex flex-col gap-1 rounded-xl border sm:rounded-2xl"
      :class="[tile.main ? 'border-night bg-night text-white' : 'border-line', compact ? 'px-3.5 py-2.5' : 'px-4 py-3 sm:py-3.5']"
    >
      <dt class="text-xs" :class="tile.main ? 'text-white/70' : 'text-ink-secondary'">{{ tile.label }}</dt>
      <dd class="font-extrabold tracking-tight whitespace-nowrap tabular-nums" :class="compact ? 'text-base sm:text-[1.0625rem]' : 'text-base sm:text-xl'">
        {{ tile.value }}
      </dd>
    </div>
  </dl>
</template>
