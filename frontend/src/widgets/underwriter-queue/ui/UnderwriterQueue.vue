<script setup lang="ts">
import { AlertTriangle, ChevronRight, Waves } from 'lucide-vue-next'
import { computed, ref, shallowRef, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { gradeTone, label, REASON_LABEL, REVIEW_LABEL, TASK_STATUS_LABEL } from '@/entities/underwriting'
import { backofficeApi, type QueueItemDto, type QueueSort, type ReviewKind } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { errorMessage, formatDateTime, formatMoney } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl, SelectField } from '@/shared/ui'

/**
 * Очередь андеррайтера с бэкенда (GET /bff/backoffice/queue): заявки, которые не решились автоматически,
 * с видом проверки, причиной маршрута, баллом скоринга и сроком по SLA. Строка ведёт в карточку заявки.
 * Статус и порядок задаёт бэкенд (status, sort), страница по 100 — «Показать ещё» догружает до total.
 * Фильтра по виду проверки в API нет — фильтруем загруженное.
 */
type Filter = 'open' | 'in_progress' | 'closed'
const FILTERS: readonly { value: Filter; label: string }[] = [
  { value: 'open', label: 'Ждут решения' },
  { value: 'in_progress', label: 'Взяты в работу' },
  { value: 'closed', label: 'Закрытые' },
]

type ReviewFilter = 'all' | ReviewKind
const REVIEW_FILTERS: readonly { value: ReviewFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'check', label: 'Проверка' },
  { value: 'dispute', label: 'Спорные' },
]

const SORTS: readonly { value: QueueSort; label: string }[] = [
  { value: 'due_at', label: 'Сначала срочные' },
  { value: 'created_at', label: 'Сначала новые' },
  { value: 'amount', label: 'По сумме' },
  { value: 'score', label: 'По баллу скоринга' },
]

const PAGE = 100

const filter = ref<Filter>('open')
const review = ref<ReviewFilter>('all')
const sort = ref<QueueSort>('due_at')

const loaded = shallowRef<QueueItemDto[]>([])
const total = ref<number | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
// Ответ старого запроса (сменили фильтр, пока грузилось) не перезаписывает новый
let requestId = 0

async function load(append = false) {
  const current = ++requestId
  loading.value = true
  error.value = null
  try {
    const page = await backofficeApi.queue({
      status: filter.value,
      sort: sort.value,
      limit: PAGE,
      offset: append ? loaded.value.length : 0,
    })
    if (current !== requestId) return
    loaded.value = append ? [...loaded.value, ...page.items] : page.items
    total.value = page.total
  } catch (caught) {
    if (current === requestId) error.value = errorMessage(caught)
  } finally {
    if (current === requestId) loading.value = false
  }
}
watch([filter, sort], () => void load(), { immediate: true })

const more = computed(() => total.value !== null && loaded.value.length < total.value)
const items = computed(() => (review.value === 'all' ? loaded.value : loaded.value.filter((item) => item.review === review.value)))

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code
</script>

<template>
  <PanelCard flush>
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
      <div class="flex flex-wrap items-center gap-3">
        <SegmentedControl v-model="filter" :options="FILTERS" label="Какие задачи показать" />
        <SegmentedControl v-model="review" :options="REVIEW_FILTERS" label="Вид проверки" />
        <SelectField v-model="sort" class="w-52" label="Порядок" hide-label :options="SORTS" dense />
      </div>
      <p v-if="total !== null" class="text-sm text-ink-secondary">
        <template v-if="review === 'all' && !more">Всего: {{ total }}</template>
        <template v-else>Показано {{ items.length }} из {{ total }}</template>
      </p>
    </div>

    <AsyncState
      :loading="loading && !loaded.length"
      :error="loaded.length ? null : error"
      :empty="!items.length"
      :empty-text="loaded.length ? 'Задач с таким видом проверки нет' : 'Задач нет — все заявки решены автоматически'"
      @retry="load()"
    >
      <div class="overflow-x-auto">
        <table class="w-full min-w-[56rem] text-left text-sm" :class="loading && 'opacity-60'">
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
            <tr v-for="item in items" :key="item.task_id" class="transition-colors hover:bg-surface-soft">
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
                  <BaseBadge v-if="item.risk_grade" :tone="gradeTone(item.risk_grade)">{{ item.risk_grade }}</BaseBadge>
                  <span class="text-ink tabular-nums">{{ item.score ?? '—' }}</span>
                  <Waves v-if="item.cash_gap" class="size-4 text-warning" aria-label="Ожидается кассовый разрыв" />
                </div>
              </td>
              <td class="px-4 py-3">
                <BaseBadge v-if="item.review" :tone="REVIEW_LABEL[item.review].tone" class="mb-1">{{ REVIEW_LABEL[item.review].label }}</BaseBadge>
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
      <div v-if="more" class="border-t border-line p-4">
        <BaseButton variant="secondary" size="s" :loading="loading" @click="load(true)">Показать ещё</BaseButton>
      </div>
      <p v-if="error && loaded.length" class="px-4 pb-4 text-sm text-brand" role="alert">{{ error }}</p>
    </AsyncState>
  </PanelCard>
</template>
