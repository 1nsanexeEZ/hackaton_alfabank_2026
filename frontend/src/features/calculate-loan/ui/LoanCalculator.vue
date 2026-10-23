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
import { founderPrescreen } from '@/entities/customer'
import { clamp, formatDate, formatMoney, formatMoneyShort, formatPercent, formatTerm, formatTermLimit } from '@/shared/lib'
import { BaseButton, RangeField, SelectField } from '@/shared/ui'

import { fitLoanParams } from '../model/loanParams'

const props = defineProps<{
  products: ProductCatalog
  /** Компании вошедшего клиента: расчёт по ставке предодобрения выбранной; гостю — пусто */
  companies?: readonly { id: string; name: string }[] | null
}>()

const emit = defineEmits<{ apply: [] }>()

const productId = defineModel<string>('productId', { required: true })
const amount = defineModel<number>('amount', { required: true })
const termMonths = defineModel<number>('termMonths', { required: true })
/** Для какой компании считать; пусто — по базовой ставке, как для гостя */
const organizationId = defineModel<string>('organizationId', { default: '' })

const product = computed(() => findProduct(props.products, productId.value))

// Для компании — только доступные ей продукты: стартапу — для стартапа, действующему бизнесу — без них
watch(organizationId, (id) => id && void founderPrescreen.load(id), { immediate: true })
const segment = computed(() => (organizationId.value ? founderPrescreen.state[organizationId.value]?.segment : undefined))
const availableProducts = computed(() =>
  segment.value ? props.products.filter((item) => Boolean(item.startupOnly) === (segment.value === 'startup')) : props.products,
)
watch(availableProducts, (list) => {
  if (list.length && !list.some((item) => item.id === productId.value)) productId.value = list[0]!.id
})

const productOptions = computed(() =>
  availableProducts.value.map((item) => ({ value: item.id, label: item.title })),
)
const companyOptions = computed(() => (props.companies ?? []).map((item) => ({ value: item.id, label: item.name })))
const company = computed(() => props.companies?.find((item) => item.id === organizationId.value) ?? null)

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

// С компанией график, ставку и причины считает бэкенд по её предодобрению; без неё — по базовой ставке продукта
const { schedule, personal, pending, estimated } = useLoanSchedule(() => ({
  product: product.value,
  amount: amount.value,
  termMonths: termMonths.value,
  organizationId: company.value?.id ?? null,
}))

const preApproved = computed(() => personal.value?.preApproved ?? null)
/** Причины, кроме «сумма/срок больше одобренного» — те объясняет блок предодобрения */
const otherProblems = computed(
  () => personal.value?.problems.filter((reason) => !reason.code.endsWith('_above_pre_approved')) ?? [],
)

function takeSuggestion() {
  const suggestion = personal.value?.suggestion
  if (!suggestion) return
  amount.value = clamp(suggestion.amount, product.value.amount.min, product.value.amount.max)
  termMonths.value = clamp(suggestion.termMonths, product.value.termMonths.min, product.value.termMonths.max)
}
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-6">
    <div class="space-y-7 rounded-card bg-white p-6 lg:p-8">
      <SelectField v-if="companyOptions.length > 1" v-model="organizationId" label="Компания" :options="companyOptions" />
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

      <div
        v-if="company && preApproved"
        class="rounded-2xl p-4 text-sm"
        :class="personal?.withinPreApproved === false ? 'bg-warning-soft' : 'bg-success-soft'"
      >
        <p class="text-ink">
          Для {{ company.name }} предварительно одобрено до <b>{{ formatMoney(preApproved.maxAmount) }}</b> от
          {{ formatPercent(preApproved.rateFrom) }}, {{ formatTermLimit(preApproved.termMaxMonths) }} — до
          {{ formatDate(preApproved.validUntil) }}
        </p>
        <template v-if="personal?.withinPreApproved === false">
          <p class="mt-2 text-ink-secondary">
            {{ personal.problems.find((reason) => reason.code.endsWith('_above_pre_approved'))?.message }}. Подать заявку
            можно, но банк может предложить меньше.
          </p>
          <button
            v-if="personal.suggestion"
            type="button"
            class="mt-2 text-left font-medium text-ink underline underline-offset-2"
            @click="takeSuggestion"
          >
            Взять одобренные условия: {{ formatMoney(personal.suggestion.amount) }} на
            {{ formatTerm(personal.suggestion.termMonths) }}, платёж {{ formatMoney(personal.suggestion.monthlyPayment) }}
          </button>
        </template>
      </div>
      <p v-else-if="company && segment === 'startup'" class="rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">
        У нового бизнеса предварительного одобрения нет: банк сначала проверяет учредителя, а условия назначает
        после оценки бизнес-плана. Расчёт — по базовой ставке продукта.
      </p>
      <p v-else-if="company && personal && personal.withinPreApproved === null" class="rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">
        Для {{ company.name }} по этому продукту предварительного одобрения нет — расчёт по базовой ставке продукта.
      </p>

      <div v-if="otherProblems.length" class="rounded-2xl bg-warning-soft p-4 text-sm">
        <p class="font-medium text-ink">{{ personal?.eligible === false ? 'Компания не подходит под продукт' : 'Обратите внимание' }}</p>
        <ul class="mt-1 space-y-0.5 text-ink-secondary">
          <li v-for="reason in otherProblems" :key="reason.code">• {{ reason.message }}</li>
        </ul>
      </div>
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
          <dd class="font-semibold">{{ personal ? '' : 'от ' }}{{ formatPercent(schedule?.rate ?? product.rateFrom) }}</dd>
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
        <template v-if="company && personal?.preApproved">Расчёт по ставке предварительного одобрения для {{ company.name }}.</template>
        <template v-else-if="company">Расчёт для {{ company.name }} по базовой ставке продукта.</template>
        <template v-else>Расчёт по базовой ставке продукта.</template>
        Точные условия банк покажет после рассмотрения заявки.
      </p>
    </div>
  </div>
</template>
