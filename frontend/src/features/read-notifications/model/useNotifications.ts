import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'

import { liveFeed } from '@/entities/notification'
import { clientApi, type FeedItemDto, type NewsDto, type OrganizationSummaryDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

const PAGE = 20

/**
 * Лента событий (`GET /feed`) и персональные новости компании (`GET /news`).
 * Новые события приходят по SSE и встают наверх; прочитанное отмечается на бэкенде.
 */
export function useNotifications() {
  const items = ref<FeedItemDto[]>([])
  const total = ref(0)
  const feedLoading = ref(false)
  const feedError = ref<string | null>(null)

  const organizations = shallowRef<OrganizationSummaryDto[]>([])
  const organizationId = ref<string>('')
  /** События одной компании; пусто — все */
  const feedOrganizationId = ref<string>('')
  const news = ref<NewsDto[]>([])
  const newsLoading = ref(false)
  const newsError = ref<string | null>(null)

  async function loadFeed(more = false) {
    feedLoading.value = true
    feedError.value = null
    try {
      const page = await clientApi.feed({
        organizationId: feedOrganizationId.value || undefined,
        limit: PAGE,
        offset: more ? items.value.length : 0,
      })
      items.value = more ? [...items.value, ...page.items.filter((item) => !items.value.some((known) => known.id === item.id))] : page.items
      total.value = page.total
    } catch (caught) {
      feedError.value = errorMessage(caught)
    } finally {
      feedLoading.value = false
    }
  }

  async function loadOrganizations() {
    if (organizations.value.length) return
    organizations.value = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
    organizationId.value ||= organizations.value[0]?.id ?? ''
  }

  async function loadNews() {
    newsLoading.value = true
    newsError.value = null
    try {
      await loadOrganizations()
      news.value = await clientApi.news(organizationId.value || undefined, 20)
    } catch (caught) {
      newsError.value = errorMessage(caught)
    } finally {
      newsLoading.value = false
    }
  }

  watch(organizationId, (next, previous) => {
    if (previous && next !== previous) void loadNews()
  })
  watch(feedOrganizationId, () => void loadFeed())

  const stopLive = liveFeed.onItem((item) => {
    const known = items.value.findIndex((entry) => entry.id === item.id)
    if (known >= 0) items.value.splice(known, 1)
    else total.value += 1
    items.value.unshift(item)
  })
  onBeforeUnmount(stopLive)

  async function markRead(item: FeedItemDto) {
    if (item.read_at) return
    item.read_at = new Date().toISOString()
    liveFeed.markedRead()
    try {
      await clientApi.readFeedItem(item.id)
    } catch {
      // Не отметилось — не страшно: при следующем открытии запись снова будет непрочитанной
    }
  }

  async function markAllRead() {
    const now = new Date().toISOString()
    items.value.forEach((item) => (item.read_at ??= now))
    const scope = feedOrganizationId.value ? { organizationId: feedOrganizationId.value } : undefined
    if (!scope) liveFeed.markedAllRead()
    try {
      await clientApi.readAllFeed(scope)
      // Прочитана только одна компания — остальное непрочитанное считает бэкенд
      if (scope) await liveFeed.refreshUnread()
    } catch (caught) {
      feedError.value = errorMessage(caught)
    }
  }

  async function markNewsRead(item: NewsDto) {
    if (item.read) return
    item.read = true
    try {
      await clientApi.readNews(item.id)
    } catch {
      // Отметка о прочтении — только для подсветки, на работу ленты не влияет
    }
  }

  return {
    items,
    total,
    feedLoading,
    feedError,
    organizations,
    organizationId,
    feedOrganizationId,
    loadOrganizations,
    news,
    newsLoading,
    newsError,
    loadFeed,
    loadNews,
    markRead,
    markAllRead,
    markNewsRead,
  }
}
