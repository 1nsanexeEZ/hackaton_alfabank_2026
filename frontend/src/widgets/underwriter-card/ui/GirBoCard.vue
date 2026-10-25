<script setup lang="ts">
import { computed } from 'vue'

import type { AccountingPeriodDto, EnrichmentDto } from '@/shared/api'
import { formatPercent } from '@/shared/lib'

import { change, millions, share } from '../model/figures'
import SourceCard from './SourceCard.vue'
import StatTile from './StatTile.vue'

/**
 * Бухотчётность ГИР БО: выручка и прибыль за последние годы мини-графиками, три коэффициента
 * и обе формы таблицами в млн ₽ — по году на колонку и изменение за последний год.
 */
const props = defineProps<{ girBo: NonNullable<EnrichmentDto['gir_bo']> }>()

/** Последние три года по порядку */
const periods = computed(() => [...props.girBo.periods].sort((a, b) => a.year - b.year).slice(-3))
const last = computed(() => periods.value[periods.value.length - 1])
const prev = computed(() => periods.value[periods.value.length - 2])

const value = (period: AccountingPeriodDto | undefined, key: keyof AccountingPeriodDto) => (period ? Number(period[key]) : 0)

/** Мини-графики: у каждого своя шкала — прибыль рядом с выручкой иначе не видна */
const CHARTS: readonly { key: keyof AccountingPeriodDto; title: string }[] = [
  { key: 'revenue', title: 'Выручка' },
  { key: 'sales_profit', title: 'Прибыль от продаж' },
  { key: 'net_profit', title: 'Чистая прибыль' },
]
const charts = computed(() =>
  CHARTS.map((chart) => {
    const values = periods.value.map((period) => value(period, chart.key))
    const max = Math.max(1, ...values.map(Math.abs))
    return {
      ...chart,
      bars: periods.value.map((period, index) => ({
        year: period.year,
        height: Math.max(3, share(Math.abs(values[index]!), max)),
        negative: values[index]! < 0,
        last: index === periods.value.length - 1,
      })),
      current: values[values.length - 1] ?? 0,
      delta: change(values[values.length - 1] ?? 0, values[values.length - 2]),
    }
  }),
)

/** Коэффициенты за последний год, рядом — прошлый */
const ratios = computed(() => {
  const ratio = (period: AccountingPeriodDto | undefined, top: keyof AccountingPeriodDto, bottom: keyof AccountingPeriodDto) => {
    const base = value(period, bottom)
    return period && base ? value(period, top) / base : null
  }
  const percent = (share: number | null) => (share === null ? '—' : formatPercent(share * 100))
  const times = (share: number | null) => (share === null ? '—' : `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(share)}×`)
  return [
    { title: 'Рентабельность по чистой прибыли', now: percent(ratio(last.value, 'net_profit', 'revenue')), before: percent(ratio(prev.value, 'net_profit', 'revenue')) },
    { title: 'Доля капитала в балансе', now: percent(ratio(last.value, 'equity', 'total_assets')), before: percent(ratio(prev.value, 'equity', 'total_assets')) },
    { title: 'Прибыль от продаж к процентам', now: times(ratio(last.value, 'sales_profit', 'interest_payable')), before: times(ratio(prev.value, 'sales_profit', 'interest_payable')) },
  ]
})

/** Строки форм; good — рост хороший (выручка, прибыль, капитал), bad — рост плохой (проценты, долги) */
const RESULTS: readonly { key: keyof AccountingPeriodDto; label: string; growth?: 'good' | 'bad' }[] = [
  { key: 'revenue', label: 'Выручка', growth: 'good' },
  { key: 'cost_of_sales', label: 'Себестоимость продаж' },
  { key: 'sales_profit', label: 'Прибыль от продаж', growth: 'good' },
  { key: 'interest_payable', label: 'Проценты к уплате', growth: 'bad' },
  { key: 'net_profit', label: 'Чистая прибыль', growth: 'good' },
]
const BALANCE: readonly { key: keyof AccountingPeriodDto; label: string; growth?: 'good' | 'bad' }[] = [
  { key: 'fixed_assets', label: 'Основные средства' },
  { key: 'inventories', label: 'Запасы' },
  { key: 'receivables', label: 'Дебиторская задолженность' },
  { key: 'cash', label: 'Денежные средства' },
  { key: 'equity', label: 'Капитал', growth: 'good' },
  { key: 'long_term_liabilities', label: 'Долгосрочные обязательства', growth: 'bad' },
  { key: 'short_term_liabilities', label: 'Краткосрочные обязательства', growth: 'bad' },
  { key: 'total_assets', label: 'Баланс (актив)' },
]

const rowsOf = (rows: typeof RESULTS) =>
  rows.map((row) => {
    const delta = change(value(last.value, row.key), prev.value ? value(prev.value, row.key) : null)
    const good = delta && row.growth ? (row.growth === 'good' ? delta.sign > 0 : delta.sign < 0) : null
    return {
      ...row,
      values: periods.value.map((period) => ({ year: period.year, amount: value(period, row.key) })),
      delta,
      tone: good === true ? 'text-success' : good === false && delta?.sign !== 0 ? 'text-brand' : 'text-ink-secondary',
    }
  })
const tables = computed(() => [
  { title: 'Финансовые результаты', rows: rowsOf(RESULTS) },
  { title: 'Баланс', rows: rowsOf(BALANCE) },
])
</script>

<template>
  <SourceCard v-if="!girBo.available || !periods.length" title="ГИР БО — бухотчётность" :status="{ tone: 'neutral', label: 'Нет данных' }">
    <p class="text-sm text-ink-secondary">{{ girBo.reason ?? 'Отчётности в ГИР БО нет' }}</p>
  </SourceCard>

  <SourceCard v-else title="ГИР БО — бухотчётность" :status="{ tone: 'neutral', label: periods.length > 1 ? `${periods[0]!.year}–${last!.year}` : String(last!.year) }" wide>
    <div class="grid grid-cols-1 gap-2.5 @lg:grid-cols-3">
      <figure v-for="chart in charts" :key="chart.key" class="m-0 min-w-0 rounded-xl bg-surface-soft px-3 pt-2.5 pb-2">
        <figcaption class="text-xs text-ink-secondary">{{ chart.title }}, млн ₽</figcaption>
        <div class="mt-2 flex h-16 items-end justify-center gap-2" role="img" :aria-label="`${chart.title}: ${chart.bars.map((bar, index) => `${bar.year} — ${millions(value(periods[index], chart.key))}`).join(', ')} млн ₽`">
          <span
            v-for="bar in chart.bars"
            :key="bar.year"
            class="w-full max-w-10 rounded-t-md"
            :class="bar.negative ? 'bg-brand' : bar.last ? 'bg-night' : 'bg-surface-strong'"
            :style="{ height: `${bar.height}%` }"
          />
        </div>
        <p class="mt-1.5 flex items-baseline justify-between gap-2">
          <span class="text-sm font-bold text-ink tabular-nums">{{ millions(chart.current) }}</span>
          <span v-if="chart.delta" class="text-xs font-semibold tabular-nums" :class="chart.delta.sign < 0 ? 'text-brand' : 'text-success'">{{ chart.delta.text }}</span>
        </p>
      </figure>
    </div>
    <div class="mt-1.5 flex flex-wrap gap-3 text-xs text-ink-secondary">
      <span v-for="(period, index) in periods" :key="period.year" class="inline-flex items-center gap-1.5">
        <span class="size-2.5 rounded-sm" :class="index === periods.length - 1 ? 'bg-night' : 'bg-surface-strong'" aria-hidden="true" />{{ period.year }}
      </span>
    </div>

    <div class="mt-3 grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-2.5">
      <StatTile v-for="ratio in ratios" :key="ratio.title" :label="ratio.title" :hint="prev ? `${prev.year} — ${ratio.before}` : null">{{ ratio.now }}</StatTile>
    </div>

    <div class="mt-3 grid grid-cols-1 gap-x-7 @3xl:grid-cols-2">
      <table v-for="table in tables" :key="table.title" class="w-full table-fixed text-sm tabular-nums">
        <colgroup>
          <col />
          <col v-for="period in periods" :key="period.year" class="w-16" />
          <col v-if="prev" class="w-14" />
        </colgroup>
        <thead class="text-xs text-ink-secondary">
          <tr>
            <th class="py-2 text-left font-semibold">{{ table.title }}</th>
            <th v-for="period in periods" :key="period.year" class="py-2 pl-3 text-right font-medium">{{ period.year }}</th>
            <th v-if="prev" class="py-2 pl-3 text-right font-medium">Изм.</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-line">
          <tr v-for="row in table.rows" :key="row.key">
            <td class="py-2 text-ink">{{ row.label }}</td>
            <td
              v-for="(cell, index) in row.values"
              :key="cell.year"
              class="py-2 pl-3 text-right"
              :class="[index === row.values.length - 1 && 'font-semibold text-ink', cell.amount < 0 && 'text-brand']"
            >
              {{ millions(cell.amount) }}
            </td>
            <td v-if="prev" class="py-2 pl-3 text-right text-xs font-semibold" :class="row.tone">{{ row.delta?.text ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="mt-1 text-xs text-ink-secondary">Суммы в млн ₽</p>
  </SourceCard>
</template>
