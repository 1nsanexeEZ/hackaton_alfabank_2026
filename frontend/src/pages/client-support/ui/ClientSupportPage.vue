<script setup lang="ts">
import { ArrowLeft, MessagesSquare, Plus } from 'lucide-vue-next'
import { computed, shallowRef, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { customer } from '@/entities/customer'
import { answeredByBank, TICKET_STATUS_META } from '@/entities/support'
import { ClientTicketChat, NewTicketForm } from '@/features/support-chat'
import { clientApi, type SupportTicketDto, type SupportTicketListItemDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { errorMessage, formatRelativeTime } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, BaseContainer, PanelCard } from '@/shared/ui'
import { openApplicationCard, openLogin } from '@/widgets/apply-flow'

/**
 * Поддержка клиента: мои обращения, чат открытого (/support/{id} — сюда ведут записи ленты) и новый вопрос
 * (?new=1, из карточки заявки — ?application=<id>). На телефоне — либо список, либо чат.
 */
const props = defineProps<{ id?: string }>()

const route = useRoute()
const router = useRouter()

const presetApplication = computed(() => (typeof route.query.application === 'string' ? route.query.application : null))
const creating = computed(() => route.query.new === '1' || Boolean(presetApplication.value))

/** «Показать ещё», пока загружено меньше total из X-Total-Count; без него — пока приходит полная страница */
const PAGE = 50

const tickets = shallowRef<SupportTicketListItemDto[] | null>(null)
const error = shallowRef<string | null>(null)
const more = shallowRef(false)
const loadingMore = shallowRef(false)

async function load(append = false) {
  error.value = null
  if (append) loadingMore.value = true
  try {
    const page = await clientApi.supportTickets({ limit: PAGE, offset: append ? (tickets.value?.length ?? 0) : 0 })
    // Свежее обращение могло сдвинуть страницы — дубли по id не берём
    const known = new Set(append ? (tickets.value ?? []).map((item) => item.id) : [])
    tickets.value = append ? [...(tickets.value ?? []), ...page.items.filter((item) => !known.has(item.id))] : page.items
    more.value = page.total !== null ? tickets.value.length < page.total : page.items.length === PAGE
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    loadingMore.value = false
  }
}

watch(
  () => customer.state.token,
  (token) => (token ? void load() : (tickets.value = null)),
  { immediate: true },
)

function onCreated(ticket: SupportTicketDto) {
  tickets.value = [ticket, ...(tickets.value ?? [])]
  void router.replace(`${ROUTE_PATH.support}/${ticket.id}`)
}

function onChanged(ticket: SupportTicketDto) {
  tickets.value = (tickets.value ?? []).map((item) => (item.id === ticket.id ? ticket : item))
}

const ask = () => void router.push({ path: ROUTE_PATH.support, query: { new: '1' } })
const showDetail = computed(() => Boolean(props.id) || creating.value)
</script>

<template>
  <section v-if="!customer.state.token" class="py-24">
    <BaseContainer class="flex flex-col items-center text-center">
      <span class="flex size-16 items-center justify-center rounded-full bg-surface text-ink-secondary">
        <MessagesSquare class="size-8" aria-hidden="true" />
      </span>
      <h1 class="text-title mt-6">Поддержка доступна после входа</h1>
      <p class="mt-3 max-w-md text-ink-secondary">Войдите, чтобы задать вопрос банку и видеть ответы специалистов.</p>
      <BaseButton class="mt-8" size="l" @click="openLogin">Войти</BaseButton>
    </BaseContainer>
  </section>

  <BaseContainer v-else class="py-10 lg:py-14">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-title">Поддержка</h1>
        <p class="mt-2 text-ink-secondary">Вопросы банку и ответы специалистов. Ответ придёт и в уведомления.</p>
      </div>
      <BaseButton @click="ask">
        <Plus class="size-4" aria-hidden="true" />
        Задать вопрос
      </BaseButton>
    </div>

    <div class="mt-8 grid items-start gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <PanelCard flush :class="showDetail && 'max-lg:hidden'">
        <AsyncState
          :loading="!tickets && !error"
          :error="error"
          :empty="Boolean(tickets) && !tickets!.length"
          empty-text="Обращений пока нет — задайте вопрос, специалист ответит здесь"
          @retry="load()"
        >
          <ul class="divide-y divide-line">
            <li v-for="ticket in tickets ?? []" :key="ticket.id">
              <RouterLink
                :to="`${ROUTE_PATH.support}/${ticket.id}`"
                class="block px-4 py-3 transition-colors hover:bg-surface-soft"
                :class="ticket.id === id && 'bg-surface-soft'"
                :aria-current="ticket.id === id ? 'page' : undefined"
              >
                <div class="flex items-start justify-between gap-2">
                  <p class="min-w-0 font-medium break-words text-ink">{{ ticket.subject }}</p>
                  <BaseBadge :tone="TICKET_STATUS_META[ticket.status].tone" class="shrink-0">
                    {{ TICKET_STATUS_META[ticket.status].label }}
                  </BaseBadge>
                </div>
                <p class="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-ink-secondary">
                  {{ ticket.number }}
                  <span v-if="ticket.last_message_at">· {{ formatRelativeTime(ticket.last_message_at) }}</span>
                  <span v-if="answeredByBank(ticket)" class="font-semibold text-brand">· ответ поддержки</span>
                </p>
              </RouterLink>
            </li>
          </ul>
          <div v-if="more" class="border-t border-line p-4">
            <BaseButton variant="secondary" size="s" :loading="loadingMore" @click="load(true)">Показать ещё</BaseButton>
          </div>
        </AsyncState>
      </PanelCard>

      <div>
        <RouterLink
          v-if="showDetail"
          :to="ROUTE_PATH.support"
          class="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-ink-secondary hover:text-ink lg:hidden"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          Все обращения
        </RouterLink>
        <PanelCard v-if="creating" title="Новый вопрос" description="Специалист банка ответит здесь же">
          <NewTicketForm :key="presetApplication ?? 'new'" :application-id="presetApplication" @created="onCreated" @cancel="router.push(ROUTE_PATH.support)" />
        </PanelCard>
        <PanelCard v-else-if="id">
          <ClientTicketChat :ticket-id="id" @changed="onChanged" @open-application="openApplicationCard" />
        </PanelCard>
        <PanelCard v-else class="max-lg:hidden">
          <div class="flex flex-col items-center py-10 text-center">
            <MessagesSquare class="size-10 text-ink-muted" aria-hidden="true" />
            <p class="mt-3 text-ink-secondary">Выберите обращение слева или задайте новый вопрос</p>
          </div>
        </PanelCard>
      </div>
    </div>
  </BaseContainer>
</template>
