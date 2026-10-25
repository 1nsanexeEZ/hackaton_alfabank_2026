<script setup lang="ts">
import { computed } from 'vue'

import type { CreditHistoryDto } from '@/shared/api'
import { formatMoney } from '@/shared/lib'

import { share } from '../model/figures'
import SourceCard from './SourceCard.vue'
import StatTile from './StatTile.vue'

/** Кредитная история (компании или руководителя): итог бейджем, три главные цифры и долги — сколько погашено */
const props = defineProps<{ title: string; history: CreditHistoryDto }>()

const KIND: Record<string, string> = {
  loan: 'кредит',
  mortgage: 'ипотека',
  card: 'кредитная карта',
  overdraft: 'овердрафт',
  credit_line: 'кредитная линия',
  leasing: 'лизинг',
  guarantee: 'гарантия',
  auto: 'автокредит',
}

const status = computed(() => {
  if (props.history.has_active_overdue) return { tone: 'brand' as const, label: 'Есть текущая просрочка' }
  if (props.history.max_overdue_days_12m > 0) return { tone: 'warning' as const, label: 'Были просрочки' }
  return { tone: 'success' as const, label: 'Просрочек нет' }
})

const obligations = computed(() =>
  props.history.obligations.map((item) => {
    const total = Number(item.amount)
    const balance = Number(item.balance)
    return { ...item, kindLabel: KIND[item.kind] ?? item.kind, repaid: total ? Math.round(share(total - balance, total)) : null }
  }),
)

const until = (date: string | null) =>
  date ? new Intl.DateTimeFormat('ru-RU', { month: 'short', year: 'numeric' }).format(new Date(date)).replace(' г.', '') : '—'
</script>

<template>
  <SourceCard :title="title" :status="status" wide>
    <div class="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-2.5">
      <StatTile label="Платежи по кредитам">
        {{ formatMoney(Number(history.total_monthly_payments)) }}<span class="text-sm font-medium text-ink-secondary"> / мес.</span>
      </StatTile>
      <StatTile label="Запросов за 30 дней">{{ history.inquiries_last_30d }}</StatTile>
      <StatTile label="Макс. просрочка за 12 мес." :tone="history.max_overdue_days_12m > 0 ? 'brand' : 'default'">
        {{ history.max_overdue_days_12m }} дн.
      </StatTile>
    </div>
    <div v-if="obligations.length" class="mt-2.5 overflow-x-auto">
      <table class="w-full min-w-[34rem] text-sm">
        <thead class="text-xs text-ink-secondary">
          <tr>
            <th class="py-2 text-left font-medium">Кредитор · вид</th>
            <th class="py-2 pl-4 text-left font-medium">Остаток из суммы</th>
            <th class="py-2 pl-3 text-right font-medium">Платёж / мес.</th>
            <th class="py-2 pl-3 text-right font-medium">До</th>
            <th class="py-2 pl-3 text-right font-medium">Просрочка</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-line tabular-nums">
          <tr v-for="(item, index) in obligations" :key="index">
            <td class="py-2.5 align-top">
              <span class="font-semibold text-ink">{{ item.creditor }}</span>
              <span class="text-ink-secondary"> · {{ item.kindLabel }}</span>
            </td>
            <td class="py-2.5 pl-4 align-top">
              {{ formatMoney(Number(item.balance)) }} <span class="text-ink-secondary">из {{ formatMoney(Number(item.amount)) }}</span>
              <span v-if="item.repaid !== null" class="mt-1.5 block h-1.5 max-w-56 overflow-hidden rounded-full bg-surface-strong" aria-hidden="true">
                <span class="block h-full rounded-full bg-success" :style="{ width: `${item.repaid}%` }" />
              </span>
              <span v-if="item.repaid !== null" class="text-[11px] text-ink-secondary">погашено {{ item.repaid }}%</span>
            </td>
            <td class="py-2.5 pl-3 text-right align-top">{{ formatMoney(Number(item.monthly_payment)) }}</td>
            <td class="py-2.5 pl-3 text-right align-top whitespace-nowrap">{{ until(item.closes_at) }}</td>
            <td class="py-2.5 pl-3 text-right align-top" :class="item.overdue_days > 0 ? 'font-semibold text-brand' : 'text-success'">
              {{ item.overdue_days }} дн.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="mt-2.5 text-sm text-ink-secondary">Действующих обязательств нет</p>
  </SourceCard>
</template>
