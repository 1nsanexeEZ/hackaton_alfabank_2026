<script setup lang="ts">
import { reactive, ref } from 'vue'

import type { FinancialReportDto, FinancialReportInput } from '@/shared/api'
import { formatMoney } from '@/shared/lib'
import { BaseButton, SelectField, TextField } from '@/shared/ui'

/** Финансовая отчётность компании: что знает банк и подача своих цифр (пересчитывает предодобрение) */
defineProps<{ reports: FinancialReportDto[]; canEdit: boolean; busy: boolean }>()

const emit = defineEmits<{ submit: [input: FinancialReportInput, done: () => void] }>()

const SOURCE: Record<FinancialReportDto['source'], string> = { declared: 'Заявлено вами', fns: 'Данные банка', bank_statement: 'По выпискам' }

const QUARTERS = [
  { value: '', label: 'Год целиком' },
  { value: '1', label: '1 квартал' },
  { value: '2', label: '2 квартал' },
  { value: '3', label: '3 квартал' },
  { value: '4', label: '4 квартал' },
] as const

const open = ref(false)
const form = reactive({
  year: String(new Date().getFullYear() - 1),
  quarter: '' as '' | '1' | '2' | '3' | '4',
  revenue: '',
  expenses: '',
  netProfit: '',
  liabilities: '',
  debtPayments: '',
})
const errors = ref<Record<string, string>>({})

const toNumber = (value: string) => Number(value.replace(/\s/g, '').replace(',', '.'))
const optional = (value: string) => (value.trim() ? toNumber(value) : null)

function period(report: FinancialReportDto) {
  return report.period_quarter ? `${report.period_quarter} кв. ${report.period_year}` : `${report.period_year} год`
}

function submit() {
  const next: Record<string, string> = {}
  const year = Number(form.year)
  if (!Number.isInteger(year) || year < 2000 || year > new Date().getFullYear()) next.year = 'Укажите год'
  if (!(toNumber(form.revenue) >= 0) || !form.revenue.trim()) next.revenue = 'Укажите выручку'
  for (const key of ['expenses', 'netProfit', 'liabilities', 'debtPayments'] as const) {
    if (form[key].trim() && !Number.isFinite(toNumber(form[key]))) next[key] = 'Введите число'
  }
  errors.value = next
  if (Object.keys(next).length) return
  emit(
    'submit',
    {
      period_year: year,
      period_quarter: form.quarter ? Number(form.quarter) : null,
      revenue: toNumber(form.revenue),
      expenses: optional(form.expenses),
      net_profit: optional(form.netProfit),
      total_liabilities: optional(form.liabilities),
      monthly_debt_payments: optional(form.debtPayments),
    },
    () => {
      open.value = false
      Object.assign(form, { revenue: '', expenses: '', netProfit: '', liabilities: '', debtPayments: '' })
    },
  )
}

const money = (value: string | null) => (value === null ? '—' : formatMoney(Number(value)))
</script>

<template>
  <section>
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h3 class="text-base font-bold text-ink">Финансовая отчётность</h3>
        <p class="mt-0.5 text-sm text-ink-secondary">По ней банк считает предварительное одобрение и оценивает риск</p>
      </div>
      <BaseButton v-if="canEdit && !open" size="s" variant="secondary" @click="open = true">Подать отчёт</BaseButton>
    </div>

    <form v-if="open" class="mt-4 space-y-4 rounded-2xl bg-surface-soft p-4" @submit.prevent="submit">
      <div class="grid gap-4 sm:grid-cols-2">
        <TextField v-model="form.year" filter="digits" label="Год" :error="errors.year" dense />
        <SelectField v-model="form.quarter" label="Период" :options="QUARTERS" dense />
        <TextField v-model="form.revenue" filter="amount" label="Выручка, ₽" :error="errors.revenue" dense required />
        <TextField v-model="form.expenses" filter="amount" label="Расходы, ₽" placeholder="Необязательно" :error="errors.expenses" dense />
        <TextField v-model="form.netProfit" label="Чистая прибыль, ₽" inputmode="decimal" placeholder="Необязательно" :error="errors.netProfit" dense />
        <TextField v-model="form.liabilities" filter="amount" label="Обязательства, ₽" placeholder="Необязательно" :error="errors.liabilities" dense />
        <TextField
          v-model="form.debtPayments"
          label="Платежи по долгам в месяц, ₽"
          inputmode="decimal"
          placeholder="Необязательно"
          :error="errors.debtPayments"
          dense
        />
      </div>
      <div class="flex flex-wrap gap-3">
        <BaseButton type="submit" size="s" :loading="busy">Отправить</BaseButton>
        <BaseButton size="s" variant="ghost" :disabled="busy" @click="open = false">Отмена</BaseButton>
      </div>
    </form>

    <p v-if="!reports.length" class="mt-3 rounded-2xl bg-surface-soft p-4 text-sm text-ink-secondary">Отчётов пока нет</p>
    <div v-else class="mt-3 overflow-x-auto rounded-2xl bg-surface-soft">
      <table class="w-full min-w-[32rem] text-left text-sm">
        <thead class="text-xs text-ink-secondary">
          <tr>
            <th class="px-4 py-2.5 font-medium">Период</th>
            <th class="px-4 py-2.5 font-medium">Источник</th>
            <th class="px-4 py-2.5 text-right font-medium">Выручка</th>
            <th class="px-4 py-2.5 text-right font-medium">Расходы</th>
            <th class="px-4 py-2.5 text-right font-medium">Прибыль</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-line">
          <tr v-for="report in reports" :key="report.id">
            <td class="px-4 py-2.5 font-medium text-ink">{{ period(report) }}</td>
            <td class="px-4 py-2.5 text-ink-secondary">{{ SOURCE[report.source] }}</td>
            <td class="px-4 py-2.5 text-right text-ink tabular-nums">{{ money(report.revenue) }}</td>
            <td class="px-4 py-2.5 text-right text-ink tabular-nums">{{ money(report.expenses) }}</td>
            <td class="px-4 py-2.5 text-right text-ink tabular-nums">{{ money(report.net_profit) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
