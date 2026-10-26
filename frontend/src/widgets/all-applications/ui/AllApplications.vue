<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { backofficeApi, type ApplicationStatusCode, type StaffApplicationDto } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { errorMessage, formatDateTime, formatMoney, formatTerm } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl, SelectField, type BadgeTone } from '@/shared/ui'

/**
 * Все заявки банка для сотрудника (GET /applications с токеном сотрудника): и черновики — клиент ещё
 * выбирает условия и проходит предскоринг, — и решённые автоматикой, которых нет в очереди задач.
 * Строка ведёт в карточку со схемой маршрута. Фильтрует бэкенд: группа статусов (status повторяется),
 * кто решил (decided_by) и компания; страница по 100, «Показать ещё» догружает следующую.
 */
const PAGE = 100

const STATUS: Record<ApplicationStatusCode, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Черновик', tone: 'neutral' },
  submitted: { label: 'Подана', tone: 'info' },
  in_review: { label: 'На рассмотрении', tone: 'info' },
  info_requested: { label: 'Запрос данных', tone: 'warning' },
  offer_ready: { label: 'Предложение', tone: 'success' },
  signing: { label: 'Подписание', tone: 'info' },
  signed: { label: 'Подписана', tone: 'success' },
  disbursed: { label: 'Кредит выдан', tone: 'success' },
  rejected: { label: 'Отказ', tone: 'brand' },
  offer_declined: { label: 'Клиент отказался', tone: 'neutral' },
  expired: { label: 'Истекла', tone: 'neutral' },
  cancelled: { label: 'Отменена', tone: 'neutral' },
}

type Group = 'all' | 'drafts' | 'review' | 'decided' | 'closed'
const GROUPS: readonly { value: Group; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'drafts', label: 'Черновики' },
  { value: 'review', label: 'На рассмотрении' },
  { value: 'decided', label: 'Решение и выдача' },
  { value: 'closed', label: 'Отказ и закрытые' },
]
const GROUP_STATUSES: Record<Exclude<Group, 'all'>, readonly ApplicationStatusCode[]> = {
  drafts: ['draft'],
  review: ['submitted', 'in_review', 'info_requested'],
  decided: ['offer_ready', 'signing', 'signed', 'disbursed'],
  closed: ['rejected', 'offer_declined', 'expired', 'cancelled'],
}

const group = ref<Group>('all')

type DecidedBy = 'any' | 'auto' | 'underwriter'
const DECIDED_BY: readonly { value: DecidedBy; label: string }[] = [
  { value: 'any', label: 'Кто угодно' },
  { value: 'auto', label: 'Автоматика' },
  { value: 'underwriter', label: 'Андеррайтер' },
]
const decidedBy = ref<DecidedBy>('any')

const organizationId = ref('')
const organizations = ref<{ value: string; label: string }[]>([])
backofficeApi
  .organizations()
  .then((list) => (organizations.value = [{ value: '', label: 'Все компании' }, ...list.map((item) => ({ value: item.id, label: `${item.name} · ${item.inn}` }))]))
  .catch(() => undefined)

const items = ref<StaffApplicationDto[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const total = ref<number | null>(null)
/** Есть ли ещё: по total из X-Total-Count, без него — пока приходит полная страница */
const more = ref(false)

async function load(append = false) {
  loading.value = true
  error.value = null
  try {
    const page = await backofficeApi.applications({
      status: group.value === 'all' ? undefined : [...GROUP_STATUSES[group.value]],
      decidedBy: decidedBy.value === 'any' ? undefined : decidedBy.value,
      organizationId: organizationId.value || undefined,
      limit: PAGE,
      offset: append ? items.value.length : 0,
    })
    items.value = append ? [...items.value, ...page.items] : page.items
    total.value = page.total
    more.value = page.total !== null ? items.value.length < page.total : page.items.length === PAGE
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    loading.value = false
  }
}
void load()
watch([group, decidedBy, organizationId], () => void load())

/** Названия компаний — по одной загрузке на компанию за сессию списка */
const companies = reactive<Record<string, { name: string; inn: string } | null>>({})
watch(
  items,
  (list) => {
    for (const id of new Set(list.map((item) => item.organization_id))) {
      if (id in companies) continue
      companies[id] = null
      backofficeApi
        .organization(id)
        .then((company) => (companies[id] = { name: company.name, inn: company.inn }))
        .catch(() => undefined)
    }
  },
  { immediate: true },
)

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code
</script>

<template>
  <PanelCard flush>
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
      <SegmentedControl v-model="group" :options="GROUPS" label="Какие заявки показать" />
      <p v-if="items.length" class="text-sm text-ink-secondary">
        <template v-if="total !== null">{{ more ? `Показано ${items.length} из ${total}` : `Всего: ${total}` }}</template>
        <template v-else>Показано {{ items.length }}{{ more ? '+' : '' }}</template>
      </p>
    </div>
    <div class="flex flex-wrap gap-3 border-b border-line px-4 py-3">
      <SelectField v-model="decidedBy" class="w-48" label="Кто решил" :options="DECIDED_BY" dense />
      <SelectField v-if="organizations.length" v-model="organizationId" class="min-w-64 flex-1 sm:max-w-md" label="Компания" :options="organizations" dense />
    </div>

    <AsyncState
      :loading="loading && !items.length"
      :error="items.length ? null : error"
      :empty="!items.length"
      :empty-text="group === 'all' && decidedBy === 'any' && !organizationId ? 'Заявок пока нет' : 'Таких заявок нет'"
      @retry="load()"
    >
      <div class="overflow-x-auto">
        <table class="w-full min-w-[52rem] text-left text-sm">
          <thead class="text-xs text-ink-secondary">
            <tr class="border-b border-line">
              <th class="px-4 py-3 font-medium">Заявка</th>
              <th class="px-4 py-3 font-medium">Компания</th>
              <th class="px-4 py-3 font-medium">Продукт и сумма</th>
              <th class="px-4 py-3 font-medium">Этап</th>
              <th class="px-4 py-3 font-medium">Обновлена</th>
              <th class="w-8 px-4 py-3" />
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <tr v-for="item in items" :key="item.id" class="transition-colors hover:bg-surface-soft">
              <td class="px-4 py-3">
                <RouterLink :to="{ name: ADMIN_ROUTE.application, params: { id: item.id } }" class="font-semibold text-ink hover:text-brand">
                  {{ item.number }}
                </RouterLink>
                <div class="mt-1">
                  <BaseBadge :tone="STATUS[item.status]?.tone ?? 'neutral'">{{ STATUS[item.status]?.label ?? item.status }}</BaseBadge>
                </div>
              </td>
              <td class="px-4 py-3">
                <template v-if="companies[item.organization_id]">
                  <p class="font-medium text-ink">{{ companies[item.organization_id]!.name }}</p>
                  <p class="text-xs text-ink-secondary">ИНН {{ companies[item.organization_id]!.inn }}</p>
                </template>
                <p v-else class="h-4 w-32 animate-pulse rounded bg-surface" aria-label="Загружаем компанию" />
              </td>
              <td class="px-4 py-3">
                <p class="text-ink">{{ productTitle(item.product_code) }}</p>
                <p class="text-xs text-ink-secondary">
                  {{ item.amount ? formatMoney(Number(item.amount)) : 'сумма не выбрана' }}<template v-if="item.term_months">
                    на {{ formatTerm(item.term_months) }}</template
                  >
                </p>
              </td>
              <td class="px-4 py-3 text-ink">
                {{ item.status === 'draft' ? 'Клиент выбирает условия' : (item.client_stage ?? '—') }}
              </td>
              <td class="px-4 py-3">
                <p class="text-ink">{{ formatDateTime(item.updated_at) }}</p>
                <p v-if="item.submitted_at" class="text-xs text-ink-secondary">подана {{ formatDateTime(item.submitted_at) }}</p>
              </td>
              <td class="px-4 py-3">
                <RouterLink
                  :to="{ name: ADMIN_ROUTE.application, params: { id: item.id } }"
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
      <p v-if="error && items.length" class="px-4 pb-4 text-sm text-brand" role="alert">{{ error }}</p>
    </AsyncState>
  </PanelCard>
</template>
