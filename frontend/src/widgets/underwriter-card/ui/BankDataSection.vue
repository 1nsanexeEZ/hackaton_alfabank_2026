<script setup lang="ts">
import { computed } from 'vue'

import type { EnrichmentDto } from '@/shared/api'
import { formatDate, formatMoney } from '@/shared/lib'

/**
 * Собственные данные банка из АБС: внутренний стоп-лист и обороты по расчётному счёту за 24 месяца.
 * Обороты дают сегмент PD-модели по месяцам в банке и лимит по оборотам, если выписки нет.
 */
const props = defineProps<{ stopList: EnrichmentDto['bank_stop_list']; turnover: EnrichmentDto['bank_turnover'] }>()

const money = (value: string | number) => formatMoney(Number(value))

const months = computed(() => [...(props.turnover?.months ?? [])].sort((a, b) => b.month.localeCompare(a.month)))
/** Поступления за последние 12 месяцев и в среднем за месяц */
const lastYear = computed(() => {
  const year = months.value.slice(0, 12)
  const inflow = year.reduce((sum, month) => sum + Number(month.inflow), 0)
  return { count: year.length, inflow, average: year.length ? inflow / year.length : 0 }
})
</script>

<template>
  <section class="text-sm lg:col-span-2">
    <p class="font-semibold text-ink">Данные банка (АБС)</p>
    <ul class="mt-2 space-y-1 text-ink">
      <li v-if="stopList" :class="stopList.listed && 'text-brand'">
        Стоп-лист банка:
        <template v-if="stopList.listed">
          в списке{{ stopList.listed_at ? ` с ${formatDate(stopList.listed_at)}` : '' }}{{ stopList.reason ? ` — ${stopList.reason}` : '' }}
        </template>
        <template v-else>нет</template>
      </li>
      <li v-if="turnover">
        <template v-if="months.length">
          Обороты по счёту: поступления за {{ lastYear.count }} мес. — {{ money(lastYear.inflow) }}, в среднем
          {{ money(lastYear.average) }} в месяц
        </template>
        <template v-else>Оборотов по счёту в банке нет</template>
        <span v-if="turnover.client_since" class="text-ink-secondary"> · клиент банка с {{ formatDate(turnover.client_since) }}</span>
      </li>
    </ul>
    <details v-if="months.length" class="mt-2 text-xs">
      <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Обороты по месяцам ({{ months.length }})</summary>
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
            <tr v-for="month in months" :key="month.month">
              <td class="py-1.5">{{ month.month }}</td>
              <td class="py-1.5 text-right">{{ money(month.inflow) }}</td>
              <td class="py-1.5 text-right">{{ money(month.outflow) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </section>
</template>
