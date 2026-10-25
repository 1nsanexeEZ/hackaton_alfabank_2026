<script setup lang="ts">
import { ref } from 'vue'

import { MessageComposer, TICKET_STATUS_META, TicketThread, useTicket } from '@/entities/support'
import { clientApi, type SupportTicketDto } from '@/shared/api'
import { errorMessage, formatDateTime } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton } from '@/shared/ui'

/**
 * Чат обращения глазами клиента (GET /support/tickets/{id}): переписка, ответ и «Закрыть обращение».
 * Решённое обращение новое сообщение вернёт в работу, в закрытое не пишут.
 */
const props = defineProps<{ ticketId: string }>()
const emit = defineEmits<{ changed: [ticket: SupportTicketDto]; openApplication: [applicationId: string] }>()

const { ticket, loading, error, reload, set } = useTicket(() => props.ticketId, (id) => clientApi.supportTicket(id))

const pending = ref<'send' | 'close' | null>(null)
const actionError = ref<string | null>(null)

async function act(kind: 'send' | 'close', request: () => Promise<SupportTicketDto>, done?: () => void) {
  pending.value = kind
  actionError.value = null
  try {
    const fresh = await request()
    set(fresh)
    emit('changed', fresh)
    done?.()
  } catch (caught) {
    actionError.value = errorMessage(caught)
    void reload(true)
  } finally {
    pending.value = null
  }
}

const send = (text: string, clear: () => void) => act('send', () => clientApi.postSupportMessage(props.ticketId, text), clear)
const close = () => act('close', () => clientApi.closeSupportTicket(props.ticketId))
</script>

<template>
  <AsyncState :loading="loading && !ticket" :error="ticket ? null : error" @retry="reload()">
    <div v-if="ticket" class="space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs text-ink-secondary">{{ ticket.number }} · создано {{ formatDateTime(ticket.created_at) }}</p>
          <h2 class="mt-0.5 text-lg font-bold break-words text-ink">{{ ticket.subject }}</h2>
          <p class="mt-1 text-sm text-ink-secondary">
            <template v-if="ticket.assignee_name">Отвечает {{ ticket.assignee_name }}</template>
            <template v-else-if="ticket.status === 'open'">Вопрос в очереди — специалист скоро возьмёт его</template>
            <button
              v-if="ticket.application_id"
              type="button"
              class="ml-2 font-medium text-brand hover:underline"
              @click="emit('openApplication', ticket.application_id)"
            >
              Открыть заявку
            </button>
          </p>
        </div>
        <BaseBadge :tone="TICKET_STATUS_META[ticket.status].tone">{{ TICKET_STATUS_META[ticket.status].label }}</BaseBadge>
      </div>

      <TicketThread :messages="ticket.messages" viewer="client" />

      <p v-if="ticket.status === 'resolved'" class="rounded-xl bg-success-soft px-4 py-3 text-sm text-ink">
        Специалист отметил вопрос решённым. Если он остался — напишите, обращение вернётся в работу.
      </p>
      <p v-if="actionError" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ actionError }}</p>

      <template v-if="ticket.status !== 'closed'">
        <MessageComposer :pending="pending === 'send'" @send="send" />
        <div class="flex justify-end">
          <BaseButton variant="ghost" size="s" :loading="pending === 'close'" @click="close">Закрыть обращение</BaseButton>
        </div>
      </template>
      <p v-else class="rounded-xl bg-surface px-4 py-3 text-sm text-ink-secondary">
        Обращение закрыто{{ ticket.closed_at ? ` ${formatDateTime(ticket.closed_at)}` : '' }}. Если появится новый вопрос — задайте его заново.
      </p>
    </div>
  </AsyncState>
</template>
