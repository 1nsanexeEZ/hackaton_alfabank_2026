<script setup lang="ts">
import { AlertTriangle, ChevronRight, Waves } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { GRADE_TONE, label, REASON_LABEL, TASK_STATUS_LABEL } from '@/entities/underwriting'
import { backofficeApi } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatDateTime, formatMoney, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, PanelCard, SegmentedControl } from '@/shared/ui'

/**
 * Очередь андеррайтера с бэкенда (GET /bff/backoffice/queue): заявки, которые не решились автоматически,
 * с причиной маршрута, баллом скоринга и сроком по SLA. Строка ведёт в карточку заявки.
 */
type Filter = 'open' | 'in_progress' | 'closed'
const FILTERS: readonly { value: Filter; label: string }[] = [
  { value: 'open', label: 'Ждут решения' },
  { value: 'in_progress', label: 'Взяты в работу' },
  { value: 'closed', label: 'Закрытые' },
]

const filter = ref<Filter>('open')
const queue = useAsyncData(() => backofficeApi.queue({ status: filter.value, limit: 100 }))
watch(filter, queue.reload)

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code
</script>

<template>
  <PanelCard flush>
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
      <SegmentedControl v-model="filter" :options="FILTERS" label="Какие задачи показать" />
      <p v-if="queue.data.value" class="text-sm text-ink-secondary">Всего: {{ queue.data.value.total }}</p>
    </div>

    <AsyncState
      :loading="queue.loading.value && !queue.data.value"
      :error="queue.error.value"
      :empty="!queue.data.value?.items.length"
      empty-text="Задач нет — все заявки решены автоматически"
      @retry="queue.reload"
    >
      <div class="overflow-x-auto">
        <table class="w-full min-w-[56rem] text-left text-sm" :class="queue.loading.value && 'opacity-60'">
          <thead class="text-xs text-ink-secondary">
            <tr class="border-b border-line">
              <th class="px-4 py-3 font-medium">Заявка</th>
              <th class="px-4 py-3 font-medium">Компания</th>
              <th class="px-4 py-3 font-medium">Продукт и сумма</th>
              <th class="px-4 py-3 font-medium">Скоринг</th>
              <th class="px-4 py-3 font-medium">Почему вручную</th>
              <th class="px-4 py-3 font-medium">Срок</th>
              <th class="w-8 px-4 py-3" />
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <tr v-for="item in queue.data.value?.items ?? []" :key="item.task_id" class="transition-colors hover:bg-surface-soft">
              <td class="px-4 py-3">
                <RouterLink
                  :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }"
                  class="font-semibold text-ink hover:text-brand"
                >
                  {{ item.number }}
                </RouterLink>
                <p class="text-xs text-ink-secondary">{{ TASK_STATUS_LABEL[item.status] ?? item.status }}</p>
              </td>
              <td class="px-4 py-3">
                <p class="font-medium text-ink">{{ item.company_name }}</p>
                <p class="text-xs text-ink-secondary">ИНН {{ item.inn }}</p>
              </td>
              <td class="px-4 py-3">
                <p class="text-ink">{{ productTitle(item.product_code) }}</p>
                <p class="text-xs text-ink-secondary">{{ item.amount ? formatMoney(Number(item.amount)) : '—' }}</p>
              </td>
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <BaseBadge v-if="item.risk_grade" :tone="GRADE_TONE[item.risk_grade] ?? 'neutral'">{{ item.risk_grade }}</BaseBadge>
                  <span class="text-ink tabular-nums">{{ item.score ?? '—' }}</span>
                  <Waves v-if="item.cash_gap" class="size-4 text-warning" aria-label="Ожидается кассовый разрыв" />
                </div>
              </td>
              <td class="px-4 py-3">
                <ul class="space-y-0.5 text-xs text-ink">
                  <li v-for="reason in item.routing_reasons" :key="reason">{{ label(REASON_LABEL, reason) }}</li>
                </ul>
              </td>
              <td class="px-4 py-3">
                <p v-if="item.due_at" class="flex items-center gap-1.5" :class="item.overdue ? 'font-medium text-brand' : 'text-ink'">
                  <AlertTriangle v-if="item.overdue" class="size-4" aria-hidden="true" />
                  {{ formatDateTime(item.due_at) }}
                </p>
                <p v-else class="text-ink-secondary">—</p>
              </td>
              <td class="px-4 py-3">
                <RouterLink
                  :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }"
                  class="flex size-8 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface hover:text-ink"
                  :aria-label="`Открыть заявку ${item.number}`"
                >
                  <ChevronRight class="size-4" aria-hidden="true" />
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AsyncState>
  </PanelCard>
</template>
