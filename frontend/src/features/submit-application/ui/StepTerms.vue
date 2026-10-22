<script setup lang="ts">
import { Building2 } from 'lucide-vue-next'
import { computed } from 'vue'

import {
  amountStep,
  PURPOSE_LABEL,
  termStep,
  useLoanSchedule,
  type ProductCatalog,
} from '@/entities/credit-product'
import type { LoanPurpose } from '@/shared/api'
import { formatMoney, formatPercent, formatTerm } from '@/shared/lib'
import { RangeField, SelectField, TextField } from '@/shared/ui'

import type { ApplicationWizard } from '../model/useApplicationWizard'

const props = defineProps<{ wizard: ApplicationWizard; products: ProductCatalog }>()

const { terms, organizations, organization, product, fieldErrors } = props.wizard

const organizationOptions = computed(() =>
  (organizations.value ?? []).map((item) => ({ value: item.id, label: `${item.name} · ИНН ${item.inn}` })),
)
const productOptions = computed(() => props.products.map((item) => ({ value: item.id, label: item.title })))
const purposeOptions = computed(() =>
  product.value.purposes.map((value) => ({ value, label: PURPOSE_LABEL[value] })),
)

const purpose = computed({
  get: () => terms.purpose as LoanPurpose,
  set: (value: LoanPurpose) => (terms.purpose = value),
})

const { schedule, pending } = useLoanSchedule(() => ({
  product: product.value,
  amount: terms.amount,
  termMonths: terms.termMonths,
}))
</script>

<template>
  <div class="space-y-6">
    <div>
      <SelectField
        v-if="organizationOptions.length > 1"
        v-model="terms.organizationId"
        label="Компания"
        :options="organizationOptions"
      />
      <div v-else-if="organization" class="flex items-center gap-3 rounded-2xl bg-surface-soft p-4">
        <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white text-ink-secondary">
          <Building2 class="size-5" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <p class="truncate font-semibold text-ink">{{ organization.name }}</p>
          <p class="text-sm text-ink-secondary">ИНН {{ organization.inn }}</p>
        </div>
      </div>
      <p v-if="fieldErrors.organization" class="mt-1.5 text-sm text-brand">{{ fieldErrors.organization }}</p>
    </div>

    <div>
      <SelectField v-model="terms.productId" label="Продукт" :options="productOptions" />
      <p v-if="fieldErrors['request.product']" class="mt-1.5 text-sm text-brand">
        {{ fieldErrors['request.product'] }}
      </p>
    </div>

    <RangeField
      v-model="terms.amount"
      label="Сумма кредита"
      :min="product.amount.min"
      :max="product.amount.max"
      :step="amountStep(product)"
      :format-value="formatMoney"
    />
    <RangeField
      v-model="terms.termMonths"
      label="Срок"
      :min="product.termMonths.min"
      :max="product.termMonths.max"
      :step="termStep(product)"
      :format-value="formatTerm"
      :editable="false"
    />

    <div class="grid gap-4 sm:grid-cols-2">
      <div>
        <SelectField v-model="purpose" label="Цель кредита" :options="purposeOptions" />
        <p v-if="fieldErrors['request.purpose']" class="mt-1.5 text-sm text-brand">
          {{ fieldErrors['request.purpose'] }}
        </p>
      </div>
      <TextField
        v-model="terms.purposeComment"
        label="Комментарий к цели"
        placeholder="Необязательно"
        :maxlength="500"
      />
    </div>

    <div class="flex flex-wrap items-baseline justify-between gap-2 rounded-2xl bg-night px-5 py-4 text-on-night">
      <span class="text-sm text-on-night-secondary">Платёж в месяц</span>
      <span class="text-xl font-bold transition-opacity" :class="pending && 'opacity-60'">
        {{ schedule ? formatMoney(schedule.monthlyPayment) : '—' }}
        <span class="text-sm font-normal text-on-night-secondary">
          по ставке от {{ formatPercent(schedule?.rate ?? product.rateFrom) }}
        </span>
      </span>
    </div>
  </div>
</template>
