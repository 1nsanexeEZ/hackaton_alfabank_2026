<script setup lang="ts">
import { ArrowRight, Newspaper } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'

import { useProductCatalog } from '@/entities/credit-product'
import { liveFeed } from '@/entities/notification'
import { formatDate, formatRelativeTime } from '@/shared/lib'
import { AsyncState, BaseButton, SegmentedControl, SelectField } from '@/shared/ui'

import { useNotifications } from '../model/useNotifications'

/** Уведомления клиента: события по заявкам (живые) и новости, подобранные под его бизнес */
const emit = defineEmits<{ openApplication: [applicationId: string]; openLink: [path: string] }>()

const notifications = useNotifications()
const { items, total, feedLoading, feedError, organizations, organizationId, feedOrganizationId, news, newsLoading, newsError } =
  notifications

const tab = ref<'events' | 'news'>('events')
const tabs = computed(() => [
  { value: 'events' as const, label: liveFeed.state.unread ? `События · ${liveFeed.state.unread}` : 'События' },
  { value: 'news' as const, label: 'Новости для вас' },
])

onMounted(() => {
  void notifications.loadFeed()
  notifications.loadOrganizations().catch(() => undefined)
})
watch(tab, (value) => value === 'news' && !news.value.length && void notifications.loadNews())

const organizationOptions = computed(() => organizations.value.map((item) => ({ value: item.id, label: item.name })))
const feedOrganizationOptions = computed(() => [{ value: '', label: 'Все компании' }, ...organizationOptions.value])
const expandedNews = ref<string | null>(null)

function openNews(id: string) {
  expandedNews.value = expandedNews.value === id ? null : id
  const item = news.value.find((entry) => entry.id === id)
  if (item && expandedNews.value) void notifications.markNewsRead(item)
}

function openEvent(id: string) {
  const item = items.value.find((entry) => entry.id === id)
  if (!item) return
  void notifications.markRead(item)
  // Ответ поддержки ведёт в чат обращения (/support/{id}), события заявки — в её карточку, если компания ещё своя
  if (item.link?.startsWith('/support/')) emit('openLink', item.link)
  else if (item.application_id && notifications.isOwnCompany(item)) emit('openApplication', item.application_id)
}

// В причинах новости бэкенд пишет код продукта («продукт CREDIT_LINE — предодобрен») — показываем название
const { products } = useProductCatalog()
const readableReason = (reason: string) =>
  reason.replace(/\b[A-Z][A-Z_]+\b/g, (code) => {
    const title = products.value?.find((product) => product.code === code)?.title
    return title ? `«${title}»` : code
  })

const PRIORITY_DOT: Record<string, string> = { high: 'bg-brand', normal: 'bg-info', low: 'bg-ink-muted' }
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <SegmentedControl v-model="tab" :options="tabs" label="Что показать" small />
      <BaseButton v-if="tab === 'events' && liveFeed.state.unread" size="s" variant="ghost" @click="notifications.markAllRead">
        Прочитать все
      </BaseButton>
    </div>

    <template v-if="tab === 'events'">
      <SelectField
        v-if="organizationOptions.length > 1"
        v-model="feedOrganizationId"
        label="События компании"
        :options="feedOrganizationOptions"
        dense
      />
      <AsyncState :loading="feedLoading && !items.length" :error="items.length ? null : feedError" @retry="notifications.loadFeed()">
        <p v-if="!items.length" class="rounded-2xl bg-surface-soft p-6 text-center text-sm text-ink-secondary">
          Событий пока нет — они появятся, когда вы подадите заявку
        </p>
        <ul v-else class="space-y-2">
          <li v-for="item in items" :key="item.id">
            <button
              type="button"
              class="w-full rounded-2xl p-4 text-left transition-colors"
              :class="item.read_at ? 'bg-surface-soft hover:bg-surface' : 'bg-info-soft hover:bg-sky'"
              @click="openEvent(item.id)"
            >
              <div class="flex items-start gap-3">
                <span
                  class="mt-1.5 size-2 shrink-0 rounded-full"
                  :class="item.read_at ? 'bg-transparent' : (PRIORITY_DOT[item.priority] ?? 'bg-info')"
                  aria-hidden="true"
                />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold text-ink">{{ item.title }}</p>
                  <p v-if="item.body" class="mt-1 text-sm whitespace-pre-line text-ink-secondary">{{ item.body }}</p>
                  <p class="mt-2 flex items-center justify-between gap-3 text-xs text-ink-muted">
                    <span>{{ formatRelativeTime(item.created_at) }}</span>
                    <span v-if="item.link?.startsWith('/support/')" class="flex items-center gap-1 font-medium text-ink-secondary">
                      К обращению <ArrowRight class="size-3.5" aria-hidden="true" />
                    </span>
                    <span v-else-if="item.application_id && notifications.isOwnCompany(item)" class="flex items-center gap-1 font-medium text-ink-secondary">
                      К заявке <ArrowRight class="size-3.5" aria-hidden="true" />
                    </span>
                    <span v-else-if="item.application_id">Нет доступа к компании</span>
                  </p>
                </div>
              </div>
            </button>
          </li>
        </ul>
        <div v-if="items.length < total" class="mt-4 text-center">
          <BaseButton size="s" variant="secondary" :loading="feedLoading" @click="notifications.loadFeed(true)">Показать ещё</BaseButton>
        </div>
      </AsyncState>
    </template>

    <template v-else>
      <SelectField
        v-if="organizationOptions.length > 1"
        v-model="organizationId"
        label="Новости для компании"
        :options="organizationOptions"
        dense
      />
      <AsyncState :loading="newsLoading && !news.length" :error="news.length ? null : newsError" @retry="notifications.loadNews">
        <p v-if="!news.length" class="rounded-2xl bg-surface-soft p-6 text-center text-sm text-ink-secondary">Новостей пока нет</p>
        <ul v-else class="space-y-2">
          <li v-for="item in news" :key="item.id" class="rounded-2xl bg-surface-soft">
            <button type="button" class="w-full p-4 text-left" :aria-expanded="expandedNews === item.id" @click="openNews(item.id)">
              <p class="flex items-start gap-2 text-sm font-semibold text-ink">
                <Newspaper class="mt-0.5 size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
                <span :class="item.read === false && 'text-ink'">{{ item.title }}</span>
              </p>
              <p class="mt-1 text-sm text-ink-secondary" :class="expandedNews === item.id ? 'whitespace-pre-line' : 'line-clamp-2'">
                {{ item.body }}
              </p>
              <p class="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
                <span>{{ formatDate(item.published_at) }}</span>
                <span
                  v-for="reason in item.relevance"
                  :key="reason"
                  class="rounded-full bg-white px-2 py-0.5 text-ink-secondary"
                  title="Почему вы видите эту новость"
                >
                  {{ readableReason(reason) }}
                </span>
              </p>
            </button>
          </li>
        </ul>
      </AsyncState>
    </template>
  </div>
</template>
