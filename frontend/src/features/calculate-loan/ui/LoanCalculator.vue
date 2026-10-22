<script setup lang="ts">
import { computed, watch } from 'vue'

import {
  amountStep,
  findProduct,
  REPAYMENT_LABEL,
  termStep,
  useLoanSchedule,
  type ProductCatalog,
} from '@/entities/credit-product'
import { formatMoney, formatMoneyShort, formatPercent, formatTerm } from '@/shared/lib'
import { BaseButton, RangeField, SelectField } from '@/shared/ui'

import { fitLoanParams } from '../model/loanParams'

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

// График считает бэкенд (POST /products/{code}/calculate) по базовой ставке и схеме продукта
const { schedule, pending, estimated } = useLoanSchedule(() => ({
  product: product.value,
  amount: amount.value,
  termMonths: termMonths.value,
}))
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
        :step="amountStep(product)"
        :format-value="formatMoney"
      />
      <RangeField
        v-model="termMonths"
        label="Срок"
        :min="product.termMonths.min"
        :max="product.termMonths.max"
        :step="termStep(product)"
        :format-value="formatTerm"
        :editable="false"
      />
    </div>

    <div class="flex flex-col rounded-card bg-night p-6 text-on-night lg:p-8" aria-live="polite">
      <p class="text-sm text-on-night-secondary">
        {{ schedule?.repayment === 'interest_only' ? 'Платёж по процентам в месяц' : 'Ежемесячный платёж' }}
      </p>
      <p
        class="mt-2 text-4xl font-bold tracking-tight transition-opacity lg:text-5xl"
        :class="pending && 'opacity-60'"
      >
        {{ schedule ? formatMoney(schedule.monthlyPayment) : '—' }}
      </p>

      <dl class="mt-8 space-y-4 border-t border-night-line pt-6 text-sm" :class="pending && 'opacity-60'">
        <div class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Ставка</dt>
          <dd class="font-semibold">от {{ formatPercent(schedule?.rate ?? product.rateFrom) }}</dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Переплата</dt>
          <dd class="font-semibold">{{ schedule ? formatMoneyShort(schedule.totalInterest) : '—' }}</dd>
        </div>
        <div class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Всего выплат</dt>
          <dd class="font-semibold">{{ schedule ? formatMoneyShort(schedule.totalPaid) : '—' }}</dd>
        </div>
        <div v-if="schedule" class="flex justify-between gap-4">
          <dt class="text-on-night-secondary">Погашение</dt>
          <dd class="text-right font-semibold">{{ REPAYMENT_LABEL[schedule.repayment] }}</dd>
        </div>
      </dl>

      <BaseButton class="mt-8 lg:mt-auto" size="l" block @click="emit('apply')">
        Оформить заявку
      </BaseButton>
      <p class="mt-4 text-xs text-on-night-secondary">
        <template v-if="estimated && !pending">Банк сейчас не отвечает — показан приблизительный расчёт. </template>
        Расчёт по базовой ставке продукта. Точные условия банк покажет после рассмотрения заявки.
      </p>
    </div>
  </div>
</template>
