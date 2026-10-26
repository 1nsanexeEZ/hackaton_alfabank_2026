import { reactive, readonly } from 'vue'

import { apiUrl, clientApi, type FeedItemDto } from '@/shared/api'

/** Событие потока: запись о заявке изменилась — карточку и списки пора перечитать */
export interface ApplicationUpdate {
  application_id: string
  organization_id: string | null
  item_id: string
  type: string
}

/**
 * Живая лента клиента: SSE `GET /feed/stream` (docs/modules/notifications.md, раздел SSE).
 * EventSource не умеет слать Authorization, поэтому поток открывается по одноразовому билету,
 * а переподключение — всегда с новым билетом и `last_event_id`, чтобы не потерять события.
 * Запускает и останавливает тот, кто знает про вход клиента (слой app).
 */
const state = reactive<{ unread: number; connected: boolean; recent: FeedItemDto[] }>({
  unread: 0,
  connected: false,
  recent: [],
})

const RETRY_MIN_MS = 1_000
const RETRY_MAX_MS = 30_000
const RECENT_LIMIT = 20

let source: EventSource | null = null
let running = false
let lastEventId: string | null = null
let retryMs = RETRY_MIN_MS
let retryTimer: ReturnType<typeof setTimeout> | undefined

const feedListeners = new Set<(item: FeedItemDto) => void>()
const applicationListeners = new Set<(update: ApplicationUpdate) => void>()
const companyListeners = new Set<() => void>()

function parse<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(event.data) as T
  } catch {
    return null
  }
}

function onFeedItem(event: MessageEvent) {
  lastEventId = event.lastEventId || lastEventId
  const item = parse<FeedItemDto>(event)
  if (!item) return
  const known = state.recent.findIndex((entry) => entry.id === item.id)
  if (known >= 0) state.recent.splice(known, 1)
  else if (!item.read_at) state.unread += 1
  state.recent.unshift(item)
  state.recent.splice(RECENT_LIMIT)
  feedListeners.forEach((listener) => listener(item))
  /*
   * Запись о составе компаний или правах, а не о заявке: добавили, сменили роль, сверка, отчётность —
   * с компанией; «Доступ к компании … закрыт» бэкенд шлёт без компании и ссылки, отличаем его от ответа
   * поддержки по типу. Кто показывает компании и права в них, перечитывает их
   */
  if (!item.application_id && (item.organization_id || item.type !== 'support')) {
    companyListeners.forEach((listener) => listener())
  }
}

function onApplicationUpdated(event: MessageEvent) {
  lastEventId = event.lastEventId || lastEventId
  const update = parse<ApplicationUpdate>(event)
  if (update) applicationListeners.forEach((listener) => listener(update))
}

async function connect() {
  if (!running) return
  try {
    const ticket = await clientApi.streamTicket()
    if (!running) return
    const url = apiUrl(ticket.stream_url) + (lastEventId ? `&last_event_id=${encodeURIComponent(lastEventId)}` : '')
    source = new EventSource(url)
    source.addEventListener('open', () => {
      state.connected = true
      retryMs = RETRY_MIN_MS
    })
    source.addEventListener('feed_item', onFeedItem)
    source.addEventListener('application_updated', onApplicationUpdated)
    // Билет одноразовый: встроенное переподключение EventSource получит 401, поэтому переподключаемся сами
    source.addEventListener('error', () => reconnect())
  } catch {
    reconnect()
  }
}

function reconnect() {
  source?.close()
  source = null
  state.connected = false
  if (!running) return
  clearTimeout(retryTimer)
  retryTimer = setTimeout(() => void connect(), retryMs)
  retryMs = Math.min(retryMs * 2, RETRY_MAX_MS)
}

async function refreshUnread(): Promise<void> {
  try {
    state.unread = (await clientApi.unreadCount()).count
  } catch {
    // Счётчик — подсказка, а не данные: без него лента всё равно открывается
  }
}

/** Клиент вошёл: счётчик непрочитанного и поток событий */
function start(): void {
  if (running) return
  running = true
  lastEventId = null
  retryMs = RETRY_MIN_MS
  void refreshUnread()
  void connect()
}

/** Клиент вышел: поток закрываем, чужие уведомления не держим */
function stop(): void {
  running = false
  clearTimeout(retryTimer)
  source?.close()
  source = null
  Object.assign(state, { unread: 0, connected: false, recent: [] })
}

/** Подписка на новые записи ленты; возвращает отписку */
function onItem(listener: (item: FeedItemDto) => void): () => void {
  feedListeners.add(listener)
  return () => feedListeners.delete(listener)
}

/** Подписка на изменения заявок; возвращает отписку */
function onApplication(listener: (update: ApplicationUpdate) => void): () => void {
  applicationListeners.add(listener)
  return () => applicationListeners.delete(listener)
}

/** Подписка на записи о компаниях (исключили, добавили, роль, сверка): списки компаний и права пора перечитать; возвращает отписку */
function onCompany(listener: () => void): () => void {
  companyListeners.add(listener)
  return () => companyListeners.delete(listener)
}

/** Прочитано в модалке: счётчик уменьшаем сразу, не дожидаясь ответа */
function markedRead(count = 1): void {
  state.unread = Math.max(0, state.unread - count)
}

function markedAllRead(): void {
  state.unread = 0
}

export const liveFeed = {
  state: readonly(state),
  start,
  stop,
  onItem,
  onApplication,
  onCompany,
  refreshUnread,
  markedRead,
  markedAllRead,
}
