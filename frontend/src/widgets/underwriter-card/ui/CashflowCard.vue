<script setup lang="ts">
import { computed } from 'vue'

import type { EnrichmentDto } from '@/shared/api'
import { formatMoney } from '@/shared/lib'

import { millions, monthLabel, niceCeil } from '../model/figures'
import SourceCard from './SourceCard.vue'
import StatTile from './StatTile.vue'

/**
 * Денежный поток по выпискам: чистый поток по месяцам столбиками (приток вверх, отток вниз), остаток
 * линией, прогноз на три месяца пунктиром на сером поле и точка кассового разрыва. Таблица — под спойлером.
 */
const props = defineProps<{ cashflow: NonNullable<EnrichmentDto['cashflow']> }>()

const W = 680
const H = 240
const PAD = { left: 48, right: 10, top: 14, bottom: 30 }
const plotW = W - PAD.left - PAD.right
const plotH = H - PAD.top - PAD.bottom

const history = computed(() => [...props.cashflow.months_history].sort((a, b) => a.month.localeCompare(b.month)))
const forecast = computed(() => [...props.cashflow.forecast].sort((a, b) => a.month.localeCompare(b.month)))

const chart = computed(() => {
  const nets = history.value.map((month) => Number(month.net))
  const balances = history.value.map((month) => Number(month.balance))
  const projected = forecast.value.map((month) => Number(month.projected_balance))
  const all = [...nets, ...balances, ...projected, 0]
  const top = niceCeil(Math.max(...all))
  const lowest = Math.min(...all)
  const bottom = lowest < 0 ? -niceCeil(-lowest) : 0
  const count = history.value.length + forecast.value.length
  const slot = plotW / Math.max(1, count)
  const y = (value: number) => PAD.top + ((top - value) / (top - bottom)) * plotH
  const x = (index: number) => PAD.left + index * slot + slot / 2
  const zero = y(0)
  const barW = Math.min(22, slot * 0.46)

  const bars = nets.map((net, index) => ({
    x: x(index) - barW / 2,
    y: Math.min(y(net), zero),
    width: barW,
    height: Math.max(1, Math.abs(y(net) - zero)),
    positive: net >= 0,
  }))
  const line = balances.map((balance, index) => `${x(index).toFixed(1)},${y(balance).toFixed(1)}`).join(' ')
  const lastIndex = balances.length - 1
  const ahead = [
    lastIndex >= 0 ? `${x(lastIndex).toFixed(1)},${y(balances[lastIndex]!).toFixed(1)}` : '',
    ...projected.map((balance, index) => `${x(history.value.length + index).toFixed(1)},${y(balance).toFixed(1)}`),
  ]
    .filter(Boolean)
    .join(' ')
  const gapIndex = props.cashflow.gap_month ? forecast.value.findIndex((month) => month.month === props.cashflow.gap_month) : -1
  const gap =
    props.cashflow.gap_detected && gapIndex >= 0
      ? { x: x(history.value.length + gapIndex), y: y(projected[gapIndex]!) }
      : null
  const ticks = [...new Set([top, top / 2, 0, ...(bottom < 0 ? [bottom] : [])])].map((value) => ({ value, y: y(value), label: millions(value) }))
  const months = [...history.value.map((month) => month.month), ...forecast.value.map((month) => month.month)].map((month, index) => ({
    x: x(index),
    label: monthLabel(month),
    year: month.slice(5, 7) === '01' || index === 0 ? month.slice(0, 4) : null,
  }))
  return {
    bars,
    line,
    ahead,
    gap,
    ticks,
    months,
    forecastX: history.value.length ? PAD.left + history.value.length * slot : null,
  }
})

const gapMonth = computed(() =>
  props.cashflow.gap_month
    ? new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(new Date(`${props.cashflow.gap_month}-01`)).replace(' г.', '')
    : null,
)
const money = (value: string | number) => formatMoney(Number(value))
</script>

<template>
  <SourceCard
    title="Денежный поток по выпискам"
    :status="cashflow.gap_detected ? { tone: 'brand', label: 'Прогноз: кассовый разрыв' } : { tone: 'success', label: 'Разрыва в прогнозе нет' }"
    wide
  >
    <div class="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-2.5">
      <StatTile v-if="cashflow.gap_detected" label="Разрыв в прогнозе" tone="brand" :hint="gapMonth">
        −{{ money(Math.abs(Number(cashflow.gap_amount ?? 0))) }}
      </StatTile>
      <StatTile v-else label="Разрыв в прогнозе" tone="success" hint="на три месяца вперёд">Нет</StatTile>
      <StatTile label="Поступления за год" hint="по выпискам">{{ money(cashflow.annual_inflow) }}</StatTile>
      <StatTile
        label="Заявленная выручка"
        :tone="cashflow.revenue_confirmed === false ? 'warning' : cashflow.revenue_confirmed ? 'success' : 'default'"
        hint="по выпискам"
      >
        {{ cashflow.revenue_confirmed === null ? 'Не сверяли' : cashflow.revenue_confirmed ? 'Подтверждена' : 'Не подтверждена' }}
      </StatTile>
    </div>

    <div class="mt-4 flex flex-wrap items-center justify-between gap-2">
      <p class="text-sm font-semibold text-ink">Чистый поток и остаток, млн ₽</p>
      <ul class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-secondary">
        <li class="flex items-center gap-1.5"><span class="size-2.5 rounded-sm bg-success" aria-hidden="true" />приток</li>
        <li class="flex items-center gap-1.5"><span class="size-2.5 rounded-sm bg-brand" aria-hidden="true" />отток</li>
        <li class="flex items-center gap-1.5"><span class="w-4 border-t-2 border-night" aria-hidden="true" />остаток</li>
        <li class="flex items-center gap-1.5"><span class="w-4 border-t-2 border-dashed border-night" aria-hidden="true" />прогноз</li>
      </ul>
    </div>
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="mt-2 block h-auto w-full"
      role="img"
      :aria-label="`Чистый поток по месяцам и прогноз остатка${cashflow.gap_detected && gapMonth ? `: кассовый разрыв в ${gapMonth}` : ''}`"
    >
      <rect v-if="chart.forecastX !== null && forecast.length" :x="chart.forecastX" :y="4" :width="W - PAD.right - chart.forecastX" :height="H - PAD.bottom - 2" rx="8" class="fill-surface-soft" />
      <text v-if="chart.forecastX !== null && forecast.length" :x="(chart.forecastX + W - PAD.right) / 2" y="18" text-anchor="middle" class="fill-ink-secondary text-[11px]">прогноз</text>
      <g v-for="tick in chart.ticks" :key="tick.value">
        <line :x1="PAD.left" :x2="W - PAD.right" :y1="tick.y" :y2="tick.y" :class="tick.value === 0 ? 'stroke-ink-muted' : 'stroke-line'" :stroke-dasharray="tick.value === 0 ? undefined : '3 4'" />
        <text :x="PAD.left - 8" :y="tick.y + 4" text-anchor="end" class="fill-ink-secondary text-[11px] tabular-nums">{{ tick.label }}</text>
      </g>
      <rect v-for="(bar, index) in chart.bars" :key="index" :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height" rx="3" :class="bar.positive ? 'fill-success' : 'fill-brand'" />
      <polyline v-if="chart.line" :points="chart.line" fill="none" class="stroke-night" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
      <polyline v-if="chart.ahead && forecast.length" :points="chart.ahead" fill="none" class="stroke-night" stroke-width="2.5" stroke-dasharray="6 5" stroke-linejoin="round" stroke-linecap="round" />
      <g v-if="chart.gap">
        <circle :cx="chart.gap.x" :cy="chart.gap.y" r="6" class="fill-brand stroke-white" stroke-width="2" />
        <text :x="chart.gap.x - 10" :y="chart.gap.y + 18" text-anchor="end" class="fill-brand text-[11px] font-bold">−{{ money(Math.abs(Number(cashflow.gap_amount ?? 0))) }}</text>
      </g>
      <text v-for="month in chart.months" :key="`${month.x}`" :x="month.x" :y="H - 12" text-anchor="middle" class="fill-ink-secondary text-[11px]">{{ month.label }}</text>
      <text v-for="month in chart.months.filter((item) => item.year)" :key="`y${month.x}`" :x="month.x" :y="H" text-anchor="middle" class="fill-ink-muted text-[10px]">{{ month.year }}</text>
    </svg>

    <details class="mt-2 text-xs">
      <summary class="cursor-pointer rounded-xl bg-surface-soft px-3.5 py-2.5 text-sm font-semibold text-ink hover:bg-surface">По месяцам · таблица</summary>
      <div class="mt-2 overflow-x-auto">
        <table class="w-full min-w-[34rem] text-left">
          <thead class="text-ink-secondary">
            <tr>
              <th class="py-1.5 font-medium">Месяц</th>
              <th class="py-1.5 text-right font-medium">Приход</th>
              <th class="py-1.5 text-right font-medium">Расход</th>
              <th class="py-1.5 text-right font-medium">Чистый поток</th>
              <th class="py-1.5 text-right font-medium">Остаток</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line tabular-nums">
            <tr v-for="month in history" :key="month.month">
              <td class="py-1.5">{{ month.month }}</td>
              <td class="py-1.5 text-right">{{ money(month.inflow) }}</td>
              <td class="py-1.5 text-right">{{ money(month.outflow) }}</td>
              <td class="py-1.5 text-right" :class="Number(month.net) < 0 ? 'text-brand' : 'text-success'">{{ money(month.net) }}</td>
              <td class="py-1.5 text-right" :class="Number(month.balance) < 0 && 'text-brand'">{{ money(month.balance) }}</td>
            </tr>
            <tr v-for="month in forecast" :key="`f-${month.month}`" class="text-ink-secondary">
              <td class="py-1.5">{{ month.month }} (прогноз)</td>
              <td class="py-1.5" colspan="3" />
              <td class="py-1.5 text-right" :class="Number(month.projected_balance) < 0 && 'text-brand'">{{ money(month.projected_balance) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </SourceCard>
</template>
