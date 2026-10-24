import type { SupportTicketListItemDto, SupportTicketStatus } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

export const TICKET_STATUS_META: Record<SupportTicketStatus, { label: string; tone: BadgeTone }> = {
  open: { label: 'Ждёт специалиста', tone: 'info' },
  in_progress: { label: 'В работе', tone: 'warning' },
  resolved: { label: 'Решено', tone: 'success' },
  closed: { label: 'Закрыто', tone: 'neutral' },
}

/** Последним писал клиент, обращение не закрыто — банк должен ответить */
export const awaitsBank = (ticket: Pick<SupportTicketListItemDto, 'status' | 'last_message_side'>) =>
  ticket.status !== 'closed' && ticket.last_message_side === 'client'

/** Последним ответил банк, обращение не закрыто — ответ ждёт клиента */
export const answeredByBank = (ticket: Pick<SupportTicketListItemDto, 'status' | 'last_message_side'>) =>
  ticket.status !== 'closed' && ticket.last_message_side === 'staff'
