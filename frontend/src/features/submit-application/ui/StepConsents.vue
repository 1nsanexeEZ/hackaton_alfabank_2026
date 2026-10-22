<script setup lang="ts">
import { computed } from 'vue'

import { PURPOSE_LABEL, useLoanSchedule } from '@/entities/credit-product'
import { formatMoney, formatPercent, formatTerm } from '@/shared/lib'
import { CheckboxField } from '@/shared/ui'

import type { ApplicationWizard } from '../model/useApplicationWizard'

const props = defineProps<{ wizard: ApplicationWizard }>()

const { terms, organization, product, consents, documents, fieldErrors } = props.wizard

const { schedule } = useLoanSchedule(() => ({
  product: product.value,
  amount: terms.amount,
  termMonths: terms.termMonths,
}))

const summary = computed(() => [
  { label: 'Компания', value: organization.value?.name ?? '—' },
  { label: 'Продукт', value: product.value.title },
  { label: 'Сумма', value: formatMoney(terms.amount) },
  { label: 'Срок', value: formatTerm(terms.termMonths) },
  { label: 'Цель', value: terms.purpose ? PURPOSE_LABEL[terms.purpose] : '—' },
  {
    label: schedule.value?.repayment === 'interest_only' ? 'Платёж по процентам в месяц' : 'Платёж в месяц',
    value: schedule.value
      ? `${formatMoney(schedule.value.monthlyPayment)} · от ${formatPercent(schedule.value.rate)}`
      : '—',
  },
  ...(documents.value.length
    ? [{ label: 'Документы', value: `${documents.value.filter((slot) => slot.files.length).length} из ${documents.value.length}` }]
    : []),
])
</script>

<template>
  <div class="space-y-6">
    <dl class="divide-y divide-line rounded-2xl bg-surface-soft px-4">
      <div v-for="row in summary" :key="row.label" class="flex justify-between gap-4 py-3 text-sm">
        <dt class="text-ink-secondary">{{ row.label }}</dt>
        <dd class="text-right font-semibold text-ink">{{ row.value }}</dd>
      </div>
    </dl>

    <div class="space-y-3">
      <CheckboxField v-model="consents.personalData" :error="fieldErrors['consents.personal_data']">
        Согласен на обработку персональных данных
      </CheckboxField>
      <CheckboxField v-model="consents.creditBureau" :error="fieldErrors['consents.credit_bureau']">
        Согласен на запрос кредитной истории компании в бюро кредитных историй
      </CheckboxField>
    </div>

    <p class="text-sm text-ink-secondary">
      После отправки банк проверит данные в ЕГРЮЛ, ФНС и БКИ и оценит риск. Решение и запросы банка появятся в
      личном кабинете — без писем и звонков.
    </p>
  </div>
</template>
