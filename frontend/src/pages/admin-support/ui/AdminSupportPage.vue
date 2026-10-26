<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed, shallowRef, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { awaitsBank, TICKET_STATUS_META } from '@/entities/support'
import { backofficeApi, type SupportTicketListItemDto, type SupportTicketStatus } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { errorMessage, formatDateTime, formatRelativeTime } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

/**
 * Очередь обращений в поддержку (GET /support/queue): «Не взятые» — открытые без исполнителя,
 * «Мои» — взятые мной, «Все». Вид — в адресе (?view=), чтобы «Назад» из обращения возвращал туда же.
 */
type View = 'unassigned' | 'mine' | 'all'
const VIEWS: readonly { value: View; label: string }[] = [
  { value: 'unassigned', label: 'Не взятые' },
  { value: 'mine', label: 'Мои' },
  { value: 'all', label: 'Все' },
]
/** Что показать во «Всех» и «Моих»; «Не взятые» — только открытые */
type StatusFilter = 'active' | 'resolved' | 'closed' | 'any'
const STATUS_FILTERS: readonly { value: StatusFilter; label: string }[] = [
  { value: 'active', label: 'В работе' },
  { value: 'resolved', label: 'Решённые' },
  { value: 'closed', label: 'Закрытые' },
  { value: 'any', label: 'Любые' },
]
const STATUSES: Record<StatusFilter, SupportTicketStatus[] | undefined> = {
  active: ['open', 'in_progress'],
  resolved: ['resolved'],
  closed: ['closed'],
  any: undefined,
}
const PAGE = 50

const route = useRoute()
const router = useRouter()
const view = computed<View>({
  get: () => (route.query.view === 'mine' || route.query.view === 'all' ? route.query.view : 'unassigned'),
  set: (next) => void router.replace({ query: { ...route.query, view: next === 'unassigned' ? undefined : next } }),
})
const statusFilter = computed<StatusFilter>({
  get: () => (['resolved', 'closed', 'any'].includes(String(route.query.status)) ? (route.query.status as StatusFilter) : 'active'),
  set: (next) => void router.replace({ query: { ...route.query, status: next === 'active' ? undefined : next } }),
})

const items = shallowRef<SupportTicketListItemDto[]>([])
const loading = shallowRef(true)
const error = shallowRef<string | null>(null)
const total = shallowRef<number | null>(null)
const more = shallowRef(false)

async function load(append = false) {
  loading.value = true
  error.value = null
  try {
    const page = await backofficeApi.supportQueue({
      scope: view.value,
      status: view.value === 'unassigned' ? ['open'] : STATUSES[statusFilter.value],
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
watch([view, statusFilter], () => void load(), { immediate: true })

const emptyText = computed(() =>
  view.value === 'unassigned' ? 'Новых обращений нет — все взяты' : view.value === 'mine' ? 'У вас нет таких обращений' : 'Обращений нет',
)
</script>

<template>
  <AdminPageHeader title="Поддержка" description="Обращения клиентов: возьмите вопрос в работу и ответьте в переписке">
    <template #actions>
      <SegmentedControl v-model="view" :options="VIEWS" label="Какие обращения показать" />
    </template>
  </AdminPageHeader>

  <PanelCard flush>
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
      <SegmentedControl v-if="view !== 'unassigned'" v-model="statusFilter" :options="STATUS_FILTERS" label="Статус" small />
      <p v-else class="text-sm text-ink-secondary">Открытые обращения без исполнителя — свежие сверху</p>
      <div class="flex items-center gap-3">
        <p v-if="total !== null" class="text-sm text-ink-secondary">
          {{ more ? `Показано ${items.length} из ${total}` : `Всего: ${total}` }}
        </p>
        <BaseButton size="s" variant="secondary" :loading="loading" @click="load()">Обновить</BaseButton>
      </div>
    </div>
    <AsyncState :loading="loading && !items.length" :error="items.length ? null : error" :empty="!items.length" :empty-text="emptyText" @retry="load()">
      <ul class="divide-y divide-line">
        <li v-for="ticket in items" :key="ticket.id">
          <RouterLink
            :to="{ name: ADMIN_ROUTE.supportTicket, params: { id: ticket.id } }"
            class="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-surface-soft"
          >
            <div class="min-w-0 flex-1">
              <p class="flex flex-wrap items-center gap-2">
                <span class="font-semibold break-words text-ink">{{ ticket.subject }}</span>
                <BaseBadge :tone="TICKET_STATUS_META[ticket.status].tone">{{ TICKET_STATUS_META[ticket.status].label }}</BaseBadge>
                <BaseBadge v-if="awaitsBank(ticket)" tone="brand">ждёт ответа</BaseBadge>
              </p>
              <p class="mt-1 text-xs text-ink-secondary">
                {{ ticket.number }} · {{ ticket.message_count }} сообщ. · создано {{ formatDateTime(ticket.created_at) }}
                <template v-if="ticket.last_message_at"> · последнее {{ formatRelativeTime(ticket.last_message_at) }}</template>
                <template v-if="ticket.application_id"> · по заявке</template>
              </p>
            </div>
            <ChevronRight class="size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
          </RouterLink>
        </li>
      </ul>
      <div v-if="more" class="border-t border-line p-4">
        <BaseButton variant="secondary" size="s" :loading="loading" @click="load(true)">Показать ещё</BaseButton>
      </div>
    </AsyncState>
  </PanelCard>
</template>
