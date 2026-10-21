<script setup lang="ts">
import { Clock } from 'lucide-vue-next'
import { computed } from 'vue'

import { formatMoneyShort, formatPercent, formatTerm } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

import { COLLATERAL_LABEL, PRODUCT_KIND_LABEL, type CreditProduct } from '../model/types'

const props = defineProps<{ product: CreditProduct }>()

const specs = computed(() => [
  { label: 'Ставка', value: `от ${formatPercent(props.product.rateFrom)}` },
  { label: 'Сумма', value: `до ${formatMoneyShort(props.product.amount.max)}` },
  { label: 'Срок', value: `до ${formatTerm(props.product.termMonths.max)}` },
  { label: 'Обеспечение', value: COLLATERAL_LABEL[props.product.collateral] },
])
</script>

<template>
  <article class="flex flex-col rounded-card bg-surface-soft p-6 lg:p-8">
    <div class="flex flex-wrap gap-2">
      <BaseBadge>{{ PRODUCT_KIND_LABEL[product.kind] }}</BaseBadge>
      <BaseBadge v-if="product.tag" tone="brand">{{ product.tag }}</BaseBadge>
    </div>

    <h3 class="text-subtitle mt-5 text-ink">{{ product.title }}</h3>
    <p class="mt-2 text-ink-secondary">{{ product.description }}</p>

    <dl class="mt-6 grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-4">
      <div v-for="spec in specs" :key="spec.label">
        <dt class="text-sm text-ink-secondary">{{ spec.label }}</dt>
        <dd class="mt-1 font-semibold text-ink">{{ spec.value }}</dd>
      </div>
    </dl>

    <p class="mt-6 flex items-center gap-2 text-sm text-ink-secondary">
      <Clock class="size-4" aria-hidden="true" />
      Решение за {{ product.decisionTime }}
    </p>

    <div v-if="$slots.actions" class="mt-auto flex flex-col gap-3 pt-6 sm:flex-row">
      <slot name="actions" />
    </div>
  </article>
</template>
