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

    <!-- Тексты согласий — по docs/personal-data.md: что обрабатываем, зачем, как отозвать -->
    <div class="space-y-4">
      <div>
        <CheckboxField v-model="consents.personalData" :error="fieldErrors['consents.personal_data']">
          Согласен на обработку персональных данных
        </CheckboxField>
        <details class="mt-1 ml-8 text-xs text-ink-secondary">
          <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Текст согласия</summary>
          <p class="mt-2">
            По ст. 9 Федерального закона № 152-ФЗ «О персональных данных» я даю согласие банку на обработку сведений
            о руководителе, участниках компании и индивидуальном предпринимателе: ФИО, должность, контакты, данные
            из ЕГРЮЛ/ЕГРИП и ФНС. Цель — рассмотрение этой кредитной заявки и сопровождение кредита. Согласие можно
            отозвать, пока заявка не отправлена; после отправки оно хранится вместе с заявкой как часть кредитного
            досье.
          </p>
        </details>
      </div>
      <div>
        <CheckboxField v-model="consents.creditBureau" :error="fieldErrors['consents.credit_bureau']">
          Согласен на запрос кредитной истории компании в бюро кредитных историй
        </CheckboxField>
        <details class="mt-1 ml-8 text-xs text-ink-secondary">
          <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Текст согласия</summary>
          <p class="mt-2">
            По ст. 6 Федерального закона № 218-ФЗ «О кредитных историях» я разрешаю банку получить кредитный отчёт
            компании (у индивидуального предпринимателя — его личный отчёт) в бюро кредитных историй, чтобы оценить
            платёжную дисциплину и долговую нагрузку. Без этого согласия банк в бюро не обращается.
          </p>
        </details>
      </div>
    </div>

    <p class="text-sm text-ink-secondary">
      После отправки банк проверит данные в ЕГРЮЛ, ФНС и БКИ и оценит риск. Решение и запросы банка появятся в
      личном кабинете — без писем и звонков.
    </p>
  </div>
</template>
