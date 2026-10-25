import { onBeforeUnmount, shallowRef, watch, type WatchSource } from 'vue'

import type { SupportTicketDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Как часто перечитываем открытое обращение: ответ собеседника появляется без перезагрузки */
const POLL_MS = 10_000

/**
 * Открытое обращение: загрузка по id и опрос, пока вкладка видна. Ответ ручки-действия
 * (сообщение, взять, закрыть…) — это свежее обращение, его кладут через set.
 */
export function useTicket(id: WatchSource<string | null>, load: (id: string) => Promise<SupportTicketDto>) {
  const ticket = shallowRef<SupportTicketDto | null>(null)
  const loading = shallowRef(false)
  const error = shallowRef<string | null>(null)
  let current: string | null = null
  let timer: ReturnType<typeof setInterval> | undefined

  async function reload(quiet = false) {
    const ticketId = current
    if (!ticketId) return
    if (!quiet) loading.value = true
    try {
      const fresh = await load(ticketId)
      if (ticketId === current) {
        ticket.value = fresh
        error.value = null
      }
    } catch (caught) {
      if (ticketId === current && !quiet) error.value = errorMessage(caught)
    } finally {
      if (ticketId === current) loading.value = false
    }
  }

  watch(
    id,
    (value) => {
      current = value
      ticket.value = null
      error.value = null
      clearInterval(timer)
      if (!value) return
      void reload()
      timer = setInterval(() => {
        if (!document.hidden && ticket.value?.status !== 'closed') void reload(true)
      }, POLL_MS)
    },
    { immediate: true },
  )
  onBeforeUnmount(() => clearInterval(timer))

  return { ticket, loading, error, reload, set: (fresh: SupportTicketDto) => (ticket.value = fresh) }
}
