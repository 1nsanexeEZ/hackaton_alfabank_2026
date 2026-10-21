<script setup lang="ts">
import type { HistoryEntry } from '@/shared/api'
import { formatDateTime } from '@/shared/lib'

import { APPLICATION_STATUS_META } from '../model/status'

/** История смены статусов — аудит: кто, когда и с каким комментарием */
defineProps<{ history: readonly HistoryEntry[] }>()
</script>

<template>
  <ol class="relative space-y-5 border-l border-line pl-5">
    <li v-for="(entry, index) in [...history].reverse()" :key="`${entry.at}-${index}`" class="relative">
      <span
        class="absolute top-1 -left-[1.625rem] size-3 rounded-full ring-4 ring-white"
        :class="index === 0 ? 'bg-brand' : 'bg-ink-muted'"
        aria-hidden="true"
      />
      <p class="text-sm font-semibold text-ink">{{ APPLICATION_STATUS_META[entry.status].label }}</p>
      <p class="mt-0.5 text-xs text-ink-secondary">
        <time :datetime="entry.at">{{ formatDateTime(entry.at) }}</time> · {{ entry.actor }}
      </p>
      <p v-if="entry.comment" class="mt-1 text-sm text-ink">{{ entry.comment }}</p>
    </li>
  </ol>
</template>
