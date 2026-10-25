import type { SupportTicketDto, SupportTicketListItemDto } from './types'

const NAMED: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }

/**
 * Тема и сообщения обращений проходят санитайзер бэкенда: `&` и `<` приходят как `&amp;` и `&lt;`.
 * Раскодируем один раз здесь — экраны выводят текст через {{ }}, без v-html.
 */
export function decodeEntities(text: string): string {
  return text.replace(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (entity, body: string) => {
    if (body[0] !== '#') return NAMED[body.toLowerCase()] ?? entity
    const code = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10)
    return Number.isFinite(code) && code <= 0x10ffff ? String.fromCodePoint(code) : entity
  })
}

export const decodeTicketItem = <T extends SupportTicketListItemDto>(ticket: T): T => ({
  ...ticket,
  subject: decodeEntities(ticket.subject),
})

export const decodeTicket = (ticket: SupportTicketDto): SupportTicketDto => ({
  ...decodeTicketItem(ticket),
  messages: ticket.messages.map((message) => ({ ...message, text: decodeEntities(message.text) })),
})
