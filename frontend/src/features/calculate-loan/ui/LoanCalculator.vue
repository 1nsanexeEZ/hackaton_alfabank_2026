<script setup lang="ts">
import { computed, watch } from 'vue'

import { findProduct, type ProductCatalog } from '@/entities/credit-product'
import { calcLoanSummary, formatMoney, formatMoneyShort, formatPercent, formatTerm } from '@/shared/lib'
import { BaseButton, RangeField, SelectField } from '@/shared/ui'

import { fitLoanParams, getAmountStep, getTermStep } from '../model/loanParams'

const props = defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{ apply: [] }>()

const productId = defineModel<string>('productId', { required: true })
const amount = defineModel<number>('amount', { required: true })
const termMonths = defineModel<number>('termMonths', { required: true })

const product = computed(() => findProduct(props.products, productId.value))

const productOptions = computed(() =>
  props.products.map((item) => ({ value: item.id, label: item.title })),
)

// При смене продукта подгоняем сумму и срок под его лимиты
watch(
  product,
  (current) => {
    const fitted = fitLoanParams(current, amount.value, termMonths.value)
    amount.value = fitted.amount
    termMonths.value = fitted.termMonths
  },
  { immediate: true },
)

const summary = computed(() => calcLoanSummary(amount.value, product.value.rateFrom, termMonths.value))
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-6">
    <div class="space-y-7 rounded-card bg-white p-6 lg:p-8">
      <SelectField v-model="productId" label="Продукт" :options="productOptions" />
      <RangeField
        v-model="amount"
        label="Сумма кредита"
        :min="product.amount.min"
        :max="product.amount.max"
        :step="getAmountStep(product)"
        :format-value="formatMoney"
      />
      <RangeField
        v-model="termMonths"
        label="Срок"
        :min="product.termMonths.min"
        :max="product.termMonths.max"
        :step="getTermStep(product)"
        :format-value="formatTerm"
        :editable="false"
      />
    </div>

    <div class="flex flex-col rounded-card bg-night p-6 text-on-night lg:p-8" aria-live="polite">
      <p class="text-sm text-on-night-secondary">Ежемесячный платёж</p>
      <p class="mt-2 text-4xl font-bold tracking-tight lg:text-5xl">
        {{ formatMoney(summary.monthlyPayment) }}
      </p>

      <dl class="mt-8 space-y-4 border-t border-night-line pt-6 text-sm">
        <div class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Ставка</dt>
          <dd class="font-semibold">от {{ formatPercent(product.rateFrom) }}</dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Переплата</dt>
          <dd class="font-semibold">{{ formatMoneyShort(summary.overpayment) }}</dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Всего выплат</dt>
          <dd class="font-semibold">{{ formatMoneyShort(summary.totalPayment) }}</dd>
        </div>
      </dl>

      <BaseButton class="mt-8 lg:mt-auto" size="l" block @click="emit('apply')">
        Оформить заявку
      </BaseButton>
      <p class="mt-4 text-xs text-on-night-secondary">
        Расчёт предварительный, платёж аннуитетный. Точные условия банк покажет после рассмотрения заявки.
      </p>
    </div>
  </div>
</template>
