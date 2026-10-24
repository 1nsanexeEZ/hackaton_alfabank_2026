<script setup lang="ts">
import { computed } from 'vue'

import type { ContractDto } from '@/shared/api'
import { formatDate, formatMoney } from '@/shared/lib'

/**
 * График платежей: итоги, диаграмма «из чего состоит платёж» и таблица целиком.
 * Таблица в общем потоке окна — без своей вертикальной прокрутки, только горизонтальная на узком экране.
 */
const props = defineProps<{ schedule: ContractDto['schedule'] }>()

const money = (value: string) => formatMoney(Number(value))
/** Копейки в таблице: «157 865,62» */
const exact = (value: string) => Number(value).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const payments = computed(() => props.schedule.payments)
const withDates = computed(() => payments.value.some((payment) => payment.due_date))

/** Высота столбика — весь платёж; красная часть — проценты, тёмная — основной долг */
const BAR_HEIGHT = 140
const bars = computed(() => {
  const largest = Math.max(...payments.value.map((payment) => Number(payment.total)), 1)
  return payments.value.map((payment, index) => {
    const height = (Number(payment.total) / largest) * BAR_HEIGHT
    const interest = Math.max(2, Math.round((Number(payment.interest) / Number(payment.total)) * height))
    const n = index + 1
    return {
      key: payment.number,
      interest,
      principal: Math.max(0, Math.round(height) - interest),
      tick: n === 1 || n === payments.value.length || n % 6 === 0 ? String(n) : '',
    }
  })
})

const first = computed(() => payments.value[0] ?? null)
const last = computed(() => payments.value[payments.value.length - 1] ?? null)
const chartLabel = computed(() =>
  first.value && last.value
    ? `Проценты в платеже: ${money(first.value.interest)} в первый месяц и ${money(last.value.interest)} в последний; остальное — основной долг`
    : 'График платежей',
)
</script>

<template>
  <div class="space-y-5">
    <dl class="grid gap-2 sm:grid-cols-3 sm:gap-3">
      <div class="rounded-xl bg-surface-soft px-4 py-3">
        <dt class="flex items-center gap-1.5 text-xs text-ink-secondary">
          <span class="size-2.5 rounded-[3px] bg-night" aria-hidden="true" />
          Основной долг
        </dt>
        <dd class="mt-1 text-lg font-extrabold tabular-nums">{{ money(schedule.amount) }}</dd>
      </div>
      <div class="rounded-xl bg-surface-soft px-4 py-3">
        <dt class="flex items-center gap-1.5 text-xs text-ink-secondary">
          <span class="size-2.5 rounded-[3px] bg-brand" aria-hidden="true" />
          Проценты за весь срок
        </dt>
        <dd class="mt-1 text-lg font-extrabold tabular-nums">{{ money(schedule.total_interest) }}</dd>
      </div>
      <div class="rounded-xl bg-surface-soft px-4 py-3">
        <dt class="text-xs text-ink-secondary">Всего выплатить</dt>
        <dd class="mt-1 text-lg font-extrabold tabular-nums">{{ money(schedule.total_paid) }}</dd>
      </div>
    </dl>

    <figure class="space-y-3 rounded-2xl border border-line px-4 pt-4 pb-3 sm:px-5">
      <figcaption class="flex flex-wrap items-baseline justify-between gap-2">
        <span class="text-[0.9375rem] font-bold text-ink">Из чего состоит каждый платёж</span>
        <span class="text-sm text-ink-secondary">{{ money(schedule.monthly_payment) }} в месяц</span>
      </figcaption>
      <div class="flex items-end gap-[3px] sm:gap-[5px]" :style="{ height: `${BAR_HEIGHT}px` }" role="img" :aria-label="chartLabel">
        <div v-for="bar in bars" :key="bar.key" class="flex flex-1 flex-col justify-end gap-0.5">
          <span class="rounded-t-[3px] bg-brand" :style="{ height: `${bar.interest}px` }" />
          <span class="rounded-b-[2px] bg-night" :style="{ height: `${bar.principal}px` }" />
        </div>
      </div>
      <div class="flex gap-[3px] sm:gap-[5px]" aria-hidden="true">
        <span v-for="bar in bars" :key="bar.key" class="flex-1 text-center text-[0.6875rem] text-ink-secondary tabular-nums">{{ bar.tick }}</span>
      </div>
      <p class="text-sm text-ink-secondary">
        <template v-if="schedule.repayment === 'annuity'">Платёж каждый месяц одинаковый. В начале большая его часть — проценты, к концу — основной долг.</template>
        <template v-else>Долг гасится равными частями, поэтому платёж с каждым месяцем меньше: проценты начисляются на остаток.</template>
      </p>
    </figure>

    <div class="space-y-2">
      <p v-if="!withDates" class="text-sm text-ink-secondary">Даты платежей появятся в договоре: первый — через месяц после выдачи.</p>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[30rem] border-collapse text-[0.8125rem] tabular-nums">
          <thead>
            <tr class="text-right text-ink-secondary">
              <th scope="col" class="border-b border-line px-2.5 py-2 text-left font-medium">№</th>
              <th v-if="withDates" scope="col" class="border-b border-line px-2.5 py-2 text-left font-medium">Дата</th>
              <th scope="col" class="border-b border-line px-2.5 py-2 font-medium">Основной долг</th>
              <th scope="col" class="border-b border-line px-2.5 py-2 font-medium">Проценты</th>
              <th scope="col" class="border-b border-line px-2.5 py-2 font-medium">Платёж</th>
              <th scope="col" class="border-b border-line px-2.5 py-2 font-medium">Остаток</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="payment in payments" :key="payment.number" class="text-right even:bg-surface-soft">
              <td class="px-2.5 py-1.5 text-left text-ink-secondary">{{ payment.number }}</td>
              <td v-if="withDates" class="px-2.5 py-1.5 text-left">{{ payment.due_date ? formatDate(payment.due_date) : '—' }}</td>
              <td class="px-2.5 py-1.5">{{ exact(payment.principal) }}</td>
              <td class="px-2.5 py-1.5">{{ exact(payment.interest) }}</td>
              <td class="px-2.5 py-1.5 font-semibold">{{ exact(payment.total) }}</td>
              <td class="px-2.5 py-1.5">{{ exact(payment.balance_after) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="text-right font-bold">
              <th scope="row" class="border-t border-line px-2.5 py-2 text-left">Итого</th>
              <td v-if="withDates" class="border-t border-line" />
              <td class="border-t border-line px-2.5 py-2">{{ exact(schedule.amount) }}</td>
              <td class="border-t border-line px-2.5 py-2">{{ exact(schedule.total_interest) }}</td>
              <td class="border-t border-line px-2.5 py-2">{{ exact(schedule.total_paid) }}</td>
              <td class="border-t border-line" />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </div>
</template>
