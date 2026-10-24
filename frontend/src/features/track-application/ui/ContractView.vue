<script setup lang="ts">
import { computed } from 'vue'

import { REPAYMENT_LABEL } from '@/entities/credit-product'
import type { ContractDto, Repayment } from '@/shared/api'
import { formatDate, formatMoney, formatPercent, formatTerm } from '@/shared/lib'

/**
 * Договор из полей GET /applications/{id}/contract: PDF бэкенд не генерирует.
 * Заёмщик, условия, график платежей и кто вправе подписать.
 */
const props = defineProps<{ contract: ContractDto }>()

const money = (value: string) => formatMoney(Number(value))

const AUTHORITY: Record<ContractDto['signers'][number]['authority'], string> = {
  registry: 'руководитель по реестру',
  power_of_attorney: 'по доверенности',
}

const borrowerIds = computed(() => {
  const { inn, ogrn, kpp } = props.contract.borrower
  return [`ИНН ${inn}`, `ОГРН ${ogrn}`, kpp && `КПП ${kpp}`].filter(Boolean).join(' · ')
})

/** Даты платежей бэкенд пока не проставляет — тогда столбец не показываем */
const withDates = computed(() => props.contract.schedule.payments.some((payment) => payment.due_date))

const terms = computed(() => {
  const { schedule, terms: offer } = props.contract
  return [
    { label: 'Сумма', value: money(schedule.amount) },
    { label: 'Срок', value: formatTerm(schedule.term_months) },
    { label: 'Ставка', value: formatPercent(Number(schedule.rate)) },
    { label: 'Платёж в месяц', value: money(schedule.monthly_payment) },
    { label: 'Проценты за весь срок', value: money(schedule.total_interest) },
    { label: 'Всего выплатить', value: money(schedule.total_paid) },
    { label: 'Погашение', value: REPAYMENT_LABEL[schedule.repayment as Repayment] ?? schedule.repayment },
    ...(props.contract.status === 'unsigned' ? [{ label: 'Предложение действует до', value: formatDate(offer.expires_at) }] : []),
  ]
})
</script>

<template>
  <div class="space-y-4 text-sm">
    <div>
      <p class="text-xs text-ink-secondary">Заёмщик</p>
      <p class="font-semibold text-ink">{{ contract.borrower.name }}</p>
      <p class="text-xs text-ink-secondary">{{ borrowerIds }}</p>
      <p v-if="contract.borrower.head_name" class="mt-1 text-xs text-ink-secondary">Руководитель: {{ contract.borrower.head_name }}</p>
    </div>

    <dl class="grid grid-cols-2 gap-2">
      <div v-for="row in terms" :key="row.label" class="rounded-lg bg-white p-2.5">
        <dt class="text-xs text-ink-secondary">{{ row.label }}</dt>
        <dd class="font-semibold text-ink tabular-nums">{{ row.value }}</dd>
      </div>
    </dl>

    <div v-if="contract.terms.conditions.length">
      <p class="text-xs text-ink-secondary">Условия</p>
      <ul class="mt-1 space-y-0.5 text-ink">
        <li v-for="condition in contract.terms.conditions" :key="condition">• {{ condition }}</li>
      </ul>
    </div>

    <details v-if="contract.schedule.payments.length">
      <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">
        График платежей · {{ contract.schedule.payments.length }}
      </summary>
      <!-- Таблица в общем потоке окна: своя вертикальная прокрутка со sticky-шапкой дёргалась при прокрутке окна -->
      <div class="mt-2 overflow-x-auto rounded-lg bg-white">
        <table class="w-full min-w-[30rem] text-left text-xs">
          <thead class="text-ink-secondary">
            <tr>
              <th class="px-2 py-1.5 font-medium">№</th>
              <th v-if="withDates" class="px-2 py-1.5 font-medium">Дата</th>
              <th class="px-2 py-1.5 text-right font-medium">Долг</th>
              <th class="px-2 py-1.5 text-right font-medium">Проценты</th>
              <th class="px-2 py-1.5 text-right font-medium">Платёж</th>
              <th class="px-2 py-1.5 text-right font-medium">Остаток</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line tabular-nums">
            <tr v-for="payment in contract.schedule.payments" :key="payment.number">
              <td class="px-2 py-1.5">{{ payment.number }}</td>
              <td v-if="withDates" class="px-2 py-1.5">{{ payment.due_date ? formatDate(payment.due_date) : '—' }}</td>
              <td class="px-2 py-1.5 text-right">{{ money(payment.principal) }}</td>
              <td class="px-2 py-1.5 text-right">{{ money(payment.interest) }}</td>
              <td class="px-2 py-1.5 text-right font-medium">{{ money(payment.total) }}</td>
              <td class="px-2 py-1.5 text-right">{{ money(payment.balance_after) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>

    <p v-if="contract.status === 'unsigned' && contract.signers.length" class="text-xs text-ink-secondary">
      Подписать могут:
      {{ contract.signers.map((signer) => `${signer.name} (${AUTHORITY[signer.authority] ?? signer.authority})`).join(', ') }}
    </p>
  </div>
</template>
