<script setup lang="ts">
import { computed } from 'vue'

import type { EnrichmentDto } from '@/shared/api'
import { formatDate, formatMoney, formatTerm } from '@/shared/lib'

import { millions, monthLabel, niceCeil, share } from '../model/figures'
import SourceCard from './SourceCard.vue'
import StatTile from './StatTile.vue'

/**
 * Собственные данные банка из АБС: внутренний стоп-лист и обороты по расчётному счёту за 24 месяца —
 * плитками и графиком поступлений и списаний по месяцам. Обороты дают сегмент PD-модели по месяцам
 * в банке и лимит по оборотам, если выписки нет.
 */
const props = defineProps<{ stopList: EnrichmentDto['bank_stop_list']; turnover: EnrichmentDto['bank_turnover'] }>()

const money = (value: string | number) => formatMoney(Number(value))

/** Месяцы по порядку — для графика; последние сверху — для таблицы */
const months = computed(() => [...(props.turnover?.months ?? [])].sort((a, b) => a.month.localeCompare(b.month)))
const newestFirst = computed(() => [...months.value].reverse())

/** Поступления и списания за последние 12 месяцев */
const lastYear = computed(() => {
  const year = months.value.slice(-12)
  const inflow = year.reduce((sum, month) => sum + Number(month.inflow), 0)
  const outflow = year.reduce((sum, month) => sum + Number(month.outflow), 0)
  return { count: year.length, inflow, average: year.length ? inflow / year.length : 0, averageOut: year.length ? outflow / year.length : 0 }
})

const clientMonths = computed(() => {
  const since = props.turnover?.client_since
  if (!since) return null
  const start = new Date(since)
  const now = new Date()
  return (now.getFullYear() - start.getFullYear()) * 12 + now.getMonth() - start.getMonth()
})

const chart = computed(() => {
  const top = niceCeil(Math.max(1, ...months.value.flatMap((month) => [Number(month.inflow), Number(month.outflow)])))
  const step = Math.max(1, Math.ceil(months.value.length / 8))
  return {
    top,
    bars: months.value.map((month, index) => ({
      month: month.month,
      inflow: share(Number(month.inflow), top),
      outflow: share(Number(month.outflow), top),
      label: index % step === 0 ? monthLabel(month.month, true) : '',
      title: `${month.month}: поступления ${money(month.inflow)}, списания ${money(month.outflow)}`,
    })),
  }
})

const status = computed(() => {
  if (props.stopList?.listed) return { tone: 'brand' as const, label: 'В стоп-листе банка' }
  if (props.stopList) return { tone: 'success' as const, label: 'Не в стоп-листе банка' }
  return null
})
</script>

<template>
  <SourceCard title="Данные банка (АБС)" :status="status" wide>
    <p v-if="stopList?.listed" class="mb-2.5 rounded-xl bg-brand-soft p-3 text-sm text-ink">
      В стоп-листе{{ stopList.listed_at ? ` с ${formatDate(stopList.listed_at)}` : '' }}{{ stopList.reason ? ` — ${stopList.reason}` : '' }}
    </p>

    <template v-if="turnover">
      <div class="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-2.5">
        <StatTile label="Клиент банка" :hint="turnover.client_since ? `с ${formatDate(turnover.client_since)}` : null">
          {{ clientMonths !== null ? formatTerm(clientMonths) : '—' }}
        </StatTile>
        <StatTile :label="`Поступления за ${lastYear.count} мес.`">{{ months.length ? money(lastYear.inflow) : '—' }}</StatTile>
        <StatTile label="В среднем в месяц" :hint="months.length ? `списания ~${millions(lastYear.averageOut)} млн ₽` : null">
          {{ months.length ? money(lastYear.average) : '—' }}
        </StatTile>
      </div>

      <template v-if="months.length">
        <div class="mt-4 flex flex-wrap items-center justify-between gap-2">
          <p class="text-sm font-semibold text-ink">Обороты по счёту за {{ months.length }} мес.</p>
          <ul class="flex gap-3 text-xs text-ink-secondary">
            <li class="flex items-center gap-1.5"><span class="size-2.5 rounded-sm bg-info" aria-hidden="true" />поступления</li>
            <li class="flex items-center gap-1.5"><span class="size-2.5 rounded-sm bg-surface-strong" aria-hidden="true" />списания</li>
          </ul>
        </div>
        <div class="relative mt-2.5 pl-12">
          <div class="absolute top-0 left-0 flex h-32 flex-col justify-between text-[11px] text-ink-secondary tabular-nums" aria-hidden="true">
            <span>{{ millions(chart.top) }} млн</span>
            <span>{{ millions(chart.top / 2) }}</span>
            <span>0</span>
          </div>
          <div class="pointer-events-none absolute top-1.5 right-0 left-12 border-t border-dashed border-line" aria-hidden="true" />
          <div class="pointer-events-none absolute top-[4.25rem] right-0 left-12 border-t border-dashed border-line" aria-hidden="true" />
          <div
            class="relative flex h-32 items-end gap-0.5 border-b border-line"
            role="img"
            :aria-label="`Поступления и списания по счёту за ${months.length} мес., в среднем ${money(lastYear.average)} поступлений в месяц`"
          >
            <div v-for="bar in chart.bars" :key="bar.month" class="flex h-full min-w-0 flex-1 items-end justify-center gap-px" :title="bar.title">
              <span class="w-[42%] max-w-2.5 rounded-t-sm bg-info" :style="{ height: `${bar.inflow}%` }" />
              <span class="w-[42%] max-w-2.5 rounded-t-sm bg-surface-strong" :style="{ height: `${bar.outflow}%` }" />
            </div>
          </div>
          <div class="mt-1.5 flex gap-0.5 text-[11px] text-ink-secondary">
            <span v-for="bar in chart.bars" :key="bar.month" class="min-w-0 flex-1 overflow-visible whitespace-nowrap">{{ bar.label }}</span>
          </div>
        </div>

        <details class="mt-3 text-xs">
          <summary class="cursor-pointer rounded-xl bg-surface-soft px-3.5 py-2.5 text-sm font-semibold text-ink hover:bg-surface">
            Обороты по месяцам · таблица, {{ months.length }}
          </summary>
          <div class="mt-2 overflow-x-auto">
            <table class="w-full min-w-[22rem] text-left">
              <thead class="text-ink-secondary">
                <tr>
                  <th class="py-1.5 font-medium">Месяц</th>
                  <th class="py-1.5 text-right font-medium">Поступления</th>
                  <th class="py-1.5 text-right font-medium">Списания</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line tabular-nums">
                <tr v-for="month in newestFirst" :key="month.month">
                  <td class="py-1.5">{{ month.month }}</td>
                  <td class="py-1.5 text-right">{{ money(month.inflow) }}</td>
                  <td class="py-1.5 text-right">{{ money(month.outflow) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </template>
      <p v-else class="mt-2.5 text-sm text-ink-secondary">Оборотов по счёту в банке нет</p>
    </template>
  </SourceCard>
</template>
