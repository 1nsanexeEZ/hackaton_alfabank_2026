<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { useSession } from '@/entities/session'
import { awaitsBank, MessageComposer, TICKET_STATUS_META, TicketThread, useTicket } from '@/entities/support'
import { ApiError, backofficeApi, type SupportTicketDto } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { errorMessage, formatDateTime } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard } from '@/shared/ui'

/**
 * Обращение глазами сотрудника (GET /support/queue/{id}). Взять может любой, но только открытое:
 * у обращения всегда один исполнитель. Отвечает, решает, закрывает и возвращает в очередь исполнитель;
 * админ — супервизор, ему это можно и во взятом другим. Обращение изменили параллельно
 * (409 version_conflict) — перечитываем и повторяем действие один раз.
 */
const props = defineProps<{ ticketId: string }>()

const { me, can } = useSession()
const { ticket, loading, error, reload, set } = useTicket(() => props.ticketId, (id) => backofficeApi.supportTicket(id))

const isMine = computed(() => Boolean(ticket.value?.assignee_id && ticket.value.assignee_id === me.value?.id))
const isSupervisor = computed(() => can('admin'))
/** Можно вести: своё или, у админа, взятое кем угодно */
const canHandle = computed(() => Boolean(ticket.value?.assignee_id) && (isMine.value || isSupervisor.value))

type Action = 'take' | 'release' | 'reply' | 'resolve' | 'close'
const pending = ref<Action | null>(null)
const actionError = ref<string | null>(null)

async function act(action: Action, request: () => Promise<SupportTicketDto>, done?: () => void, retried = false): Promise<void> {
  pending.value = action
  actionError.value = null
  try {
    set(await request())
    done?.()
  } catch (caught) {
    if (caught instanceof ApiError && caught.details.code === 'version_conflict' && !retried) {
      await reload(true)
      return act(action, request, done, true)
    }
    actionError.value = errorMessage(caught)
    // Взяли раньше нас — карточка покажет, кто
    await reload(true)
  } finally {
    pending.value = null
  }
}

const id = () => props.ticketId
const take = () => act('take', () => backofficeApi.takeSupportTicket(id()))
const release = () => act('release', () => backofficeApi.releaseSupportTicket(id()))
const resolve = () => act('resolve', () => backofficeApi.resolveSupportTicket(id()))
const close = () => act('close', () => backofficeApi.closeSupportTicketByStaff(id()))
const reply = (text: string, clear: () => void) => act('reply', () => backofficeApi.replySupportTicket(id(), text), clear)

/** Название компании обращения — из карточки компании */
const company = shallowRef<{ name: string; inn: string } | null>(null)
watch(
  () => ticket.value?.organization_id,
  (organizationId) => {
    company.value = null
    if (!organizationId) return
    backofficeApi
      .organization(organizationId)
      .then((item) => (company.value = { name: item.name, inn: item.inn }))
      .catch(() => undefined)
  },
  { immediate: true },
)
</script>

<template>
  <AsyncState :loading="loading && !ticket" :error="ticket ? null : error" @retry="reload()">
    <div v-if="ticket" class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <PanelCard :title="ticket.subject" :description="`${ticket.number} · создано ${formatDateTime(ticket.created_at)}`">
        <template #actions>
          <BaseBadge v-if="awaitsBank(ticket)" tone="brand">ждёт ответа</BaseBadge>
          <BaseBadge :tone="TICKET_STATUS_META[ticket.status].tone">{{ TICKET_STATUS_META[ticket.status].label }}</BaseBadge>
        </template>
        <div class="space-y-4">
          <TicketThread :messages="ticket.messages" viewer="staff" />
          <p v-if="actionError" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ actionError }}</p>
          <template v-if="ticket.status !== 'closed'">
            <MessageComposer
              v-if="canHandle"
              :pending="pending === 'reply'"
              placeholder="Ответ клиенту"
              @send="reply"
            />
            <p v-else-if="ticket.assignee_id" class="rounded-xl bg-surface px-4 py-3 text-sm text-ink-secondary">
              Обращение ведёт {{ ticket.assignee_name ?? 'другой сотрудник' }} — отвечает он.
            </p>
            <p v-else class="rounded-xl bg-surface px-4 py-3 text-sm text-ink-secondary">
              Чтобы ответить, возьмите обращение — тогда оно закрепится за вами.
            </p>
          </template>
        </div>
      </PanelCard>

      <div class="space-y-4">
        <PanelCard title="Обращение">
          <dl class="space-y-3 text-sm">
            <div>
              <dt class="text-ink-secondary">Клиент</dt>
              <dd class="text-ink">{{ ticket.author_name ?? '—' }}</dd>
            </div>
            <div v-if="ticket.organization_id">
              <dt class="text-ink-secondary">Компания</dt>
              <dd class="text-ink">{{ company ? `${company.name}, ИНН ${company.inn}` : '…' }}</dd>
            </div>
            <div v-if="ticket.application_id">
              <dt class="text-ink-secondary">Заявка</dt>
              <dd>
                <RouterLink
                  :to="{ name: ADMIN_ROUTE.application, params: { id: ticket.application_id } }"
                  class="font-medium text-brand hover:underline"
                >
                  Открыть карточку заявки
                </RouterLink>
              </dd>
            </div>
            <div>
              <dt class="text-ink-secondary">Исполнитель</dt>
              <dd class="text-ink">
                <template v-if="ticket.assignee_id">
                  {{ isMine ? 'вы' : (ticket.assignee_name ?? 'сотрудник') }}{{ ticket.taken_at ? `, с ${formatDateTime(ticket.taken_at)}` : '' }}
                </template>
                <template v-else>никто не взял</template>
              </dd>
            </div>
            <div v-if="ticket.resolved_at">
              <dt class="text-ink-secondary">Решено</dt>
              <dd class="text-ink">{{ formatDateTime(ticket.resolved_at) }}</dd>
            </div>
          </dl>
        </PanelCard>

        <div v-if="ticket.status !== 'closed'" class="flex flex-col gap-2">
          <BaseButton v-if="ticket.status === 'open' && !ticket.assignee_id" :loading="pending === 'take'" block @click="take">
            Взять в работу
          </BaseButton>
          <template v-if="canHandle">
            <BaseButton v-if="ticket.status === 'in_progress'" variant="secondary" :loading="pending === 'resolve'" block @click="resolve">
              Решено
            </BaseButton>
            <BaseButton v-if="ticket.status === 'in_progress'" variant="secondary" :loading="pending === 'release'" block @click="release">
              Вернуть в очередь
            </BaseButton>
            <BaseButton variant="ghost" :loading="pending === 'close'" block @click="close">Закрыть обращение</BaseButton>
          </template>
          <p v-if="isSupervisor && ticket.assignee_id && !isMine" class="text-xs text-ink-secondary">
            Вы — администратор: можете ответить и закрыть обращение, исполнитель не изменится.
          </p>
        </div>
      </div>
    </div>
  </AsyncState>
</template>
