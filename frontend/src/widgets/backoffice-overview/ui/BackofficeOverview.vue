<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { backofficeApi } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatDate, useAsyncData } from '@/shared/lib'
import { AsyncState, PanelCard } from '@/shared/ui'

/** Обзор бэк-офиса на метриках бэкенда (GET /bff/backoffice/metrics) и очереди специалиста */
const metrics = useAsyncData(() => backofficeApi.metrics())
const queue = useAsyncData(() => backofficeApi.queue({ status: 'open', limit: 100 }))

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code

function duration(seconds: number | null) {
  if (seconds === null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} с`
  if (seconds < 3600) return `${Math.round(seconds / 60)} мин`
  return `${(seconds / 3600).toFixed(1)} ч`
}

const tiles = computed(() => {
  const data = metrics.data.value
  const open = queue.data.value
  return [
    { label: 'Подано заявок', value: data ? String(data.submitted) : '—' },
    { label: 'Решено', value: data ? String(data.decided) : '—' },
    { label: 'Решено автоматически', value: data?.auto_decision_share != null ? `${Math.round(data.auto_decision_share * 100)}%` : '—' },
    { label: 'Среднее время до решения', value: duration(data?.avg_time_to_decision_sec ?? null) },
    { label: 'Ждут специалиста', value: open ? String(open.total) : '—' },
    { label: 'Просрочено по SLA', value: open ? String(open.items.filter((item) => item.overdue).length) : '—' },
  ]
})

/** Сводка по продуктам за период */
const byProduct = computed(() => {
  const rows = metrics.data.value?.rows ?? []
  const map = new Map<string, { submitted: number; approved: number; counter: number; rejected: number; manual: number }>()
  for (const row of rows) {
    const entry = map.get(row.product_code) ?? { submitted: 0, approved: 0, counter: 0, rejected: 0, manual: 0 }
    entry.submitted += row.submitted
    entry.approved += row.approved
    entry.counter += row.counter_offers
    entry.rejected += row.rejected
    entry.manual += row.manual_reviews
    map.set(row.product_code, entry)
  }
  return [...map.entries()].map(([code, value]) => ({ code, ...value })).sort((a, b) => b.submitted - a.submitted)
})

/** Подано по дням */
const byDay = computed(() => {
  const days = new Map<string, number>()
  for (const row of metrics.data.value?.rows ?? []) days.set(row.day, (days.get(row.day) ?? 0) + row.submitted)
  const list = [...days.entries()].sort(([a], [b]) => a.localeCompare(b))
  const max = Math.max(1, ...list.map(([, count]) => count))
  return list.map(([day, count]) => ({ day, count, height: Math.max(6, (count / max) * 100) }))
})
</script>

<template>
  <AsyncState :loading="metrics.loading.value && !metrics.data.value" :error="metrics.error.value" @retry="metrics.reload">
    <div class="space-y-4">
      <ul class="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <li v-for="tile in tiles" :key="tile.label" class="rounded-card bg-white p-4 ring-1 ring-line">
          <p class="text-2xl font-bold text-ink tabular-nums">{{ tile.value }}</p>
          <p class="mt-1 text-xs text-ink-secondary">{{ tile.label }}</p>
        </li>
      </ul>

      <div class="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
        <PanelCard
          title="Заявки по продуктам"
          :description="metrics.data.value ? `${formatDate(metrics.data.value.date_from)} — ${formatDate(metrics.data.value.date_to)}` : undefined"
        >
          <p v-if="!byProduct.length" class="text-sm text-ink-secondary">За период заявок не было</p>
          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[30rem] text-left text-sm">
              <thead class="text-xs text-ink-secondary">
                <tr>
                  <th class="py-2 font-medium">Продукт</th>
                  <th class="py-2 text-right font-medium">Подано</th>
                  <th class="py-2 text-right font-medium">Одобрено</th>
                  <th class="py-2 text-right font-medium">Контр.</th>
                  <th class="py-2 text-right font-medium">Отказ</th>
                  <th class="py-2 text-right font-medium">Вручную</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line tabular-nums">
                <tr v-for="row in byProduct" :key="row.code">
                  <td class="py-2 text-ink">{{ productTitle(row.code) }}</td>
                  <td class="py-2 text-right">{{ row.submitted }}</td>
                  <td class="py-2 text-right text-success">{{ row.approved }}</td>
                  <td class="py-2 text-right text-warning">{{ row.counter }}</td>
                  <td class="py-2 text-right text-brand">{{ row.rejected }}</td>
                  <td class="py-2 text-right text-info">{{ row.manual }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </PanelCard>

        <PanelCard title="Подано по дням">
          <p v-if="!byDay.length" class="text-sm text-ink-secondary">За период заявок не было</p>
          <div v-else class="flex h-40 items-end gap-2" role="img" aria-label="Количество поданных заявок по дням">
            <div v-for="bar in byDay" :key="bar.day" class="flex flex-1 flex-col items-center gap-1">
              <span class="text-xs text-ink tabular-nums">{{ bar.count }}</span>
              <span class="w-full max-w-10 rounded-t-md bg-brand" :style="{ height: `${bar.height}%` }" />
              <span class="text-[10px] text-ink-secondary">{{ bar.day.slice(5) }}</span>
            </div>
          </div>
          <RouterLink :to="{ name: ADMIN_ROUTE.applications }" class="mt-4 inline-block text-sm font-medium text-brand hover:underline">
            К очереди заявок →
          </RouterLink>
        </PanelCard>
      </div>
    </div>
  </AsyncState>
</template>
