<script setup lang="ts">
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'

import { liveFeed } from '@/entities/notification'
import { clientApi, type FeedItemDto } from '@/shared/api'
import { errorMessage, formatRelativeTime } from '@/shared/lib'
import { AsyncState, BaseButton } from '@/shared/ui'

/**
 * Уведомления по одной заявке: GET /feed?application_id= (и unread_only), «прочитать все» — только её
 * (POST /feed/read-all?application_id=). Новые записи этой заявки приходят из живой ленты.
 */
const props = defineProps<{ applicationId: string }>()

const PAGE = 20

const items = ref<FeedItemDto[]>([])
const total = ref(0)
const unreadOnly = ref(false)
const loading = ref(false)
const error = shallowRef<string | null>(null)

async function load(more = false) {
  loading.value = true
  error.value = null
  try {
    const page = await clientApi.feed({
      applicationId: props.applicationId,
      unreadOnly: unreadOnly.value,
      limit: PAGE,
      offset: more ? items.value.length : 0,
    })
    const known = new Set(more ? items.value.map((item) => item.id) : [])
    items.value = more ? [...items.value, ...page.items.filter((item) => !known.has(item.id))] : page.items
    total.value = page.total
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    loading.value = false
  }
}
watch([() => props.applicationId, unreadOnly], () => void load(), { immediate: true })

const stopLive = liveFeed.onItem((item) => {
  if (item.application_id !== props.applicationId) return
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
    // Не отметилось — при следующем открытии запись снова будет непрочитанной
  }
}

async function markAllRead() {
  const now = new Date().toISOString()
  items.value.forEach((item) => (item.read_at ??= now))
  try {
    await clientApi.readAllFeed({ applicationId: props.applicationId })
    // Прочитана только эта заявка — общий счётчик пересчитывает бэкенд
    await liveFeed.refreshUnread()
    if (unreadOnly.value) await load()
  } catch (caught) {
    error.value = errorMessage(caught)
  }
}

const PRIORITY_DOT: Record<string, string> = { high: 'bg-brand', normal: 'bg-info', low: 'bg-ink-muted' }
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <label class="flex cursor-pointer items-center gap-2 text-sm text-ink">
        <input v-model="unreadOnly" type="checkbox" class="size-4 accent-brand" />
        Только непрочитанные
      </label>
      <BaseButton v-if="items.some((item) => !item.read_at)" size="s" variant="ghost" @click="markAllRead">Прочитать все</BaseButton>
    </div>

    <AsyncState :loading="loading && !items.length" :error="items.length ? null : error" @retry="load()">
      <p v-if="!items.length" class="rounded-2xl bg-surface-soft p-6 text-center text-sm text-ink-secondary">
        {{ unreadOnly ? 'Непрочитанных уведомлений по заявке нет' : 'Уведомлений по заявке пока нет' }}
      </p>
      <ul v-else class="space-y-2">
        <li v-for="item in items" :key="item.id">
          <button
            type="button"
            class="w-full rounded-2xl p-4 text-left transition-colors"
            :class="item.read_at ? 'bg-surface-soft hover:bg-surface' : 'bg-info-soft hover:bg-sky'"
            @click="markRead(item)"
          >
            <span class="flex items-start gap-3">
              <span
                class="mt-1.5 size-2 shrink-0 rounded-full"
                :class="item.read_at ? 'bg-transparent' : (PRIORITY_DOT[item.priority] ?? 'bg-info')"
                aria-hidden="true"
              />
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-semibold text-ink">{{ item.title }}</span>
                <span v-if="item.body" class="mt-1 block text-sm whitespace-pre-line text-ink-secondary">{{ item.body }}</span>
                <span class="mt-2 block text-xs text-ink-muted">{{ formatRelativeTime(item.created_at) }}</span>
              </span>
            </span>
          </button>
        </li>
      </ul>
      <div v-if="items.length < total" class="mt-4 text-center">
        <BaseButton size="s" variant="secondary" :loading="loading" @click="load(true)">Показать ещё</BaseButton>
      </div>
      <p v-if="error && items.length" class="mt-2 text-sm text-brand" role="alert">{{ error }}</p>
    </AsyncState>
  </div>
</template>
