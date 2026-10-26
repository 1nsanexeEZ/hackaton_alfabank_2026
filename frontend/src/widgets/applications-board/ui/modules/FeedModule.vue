<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { ADMIN_ROUTE } from '@/shared/config'
import { formatMoney, formatRelativeTime } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

import { STATUS, TRACK, trackProgress } from '../../model/status'
import { toAmount, useBoard } from '../../model/useBoardData'

const { overview } = useBoard()

/** Последние изменённые заявки — карточками с трекером этапов, как в кабинете клиента; порядок задаёт бэкенд */
const items = computed(() => (overview.value?.latest ?? []).map((item) => ({ ...item, progress: trackProgress(item.status) })))
</script>

<template>
  <ul class="grid gap-3 md:grid-cols-2">
    <li v-for="item in items" :key="item.application_id">
      <RouterLink
        :to="{ name: ADMIN_ROUTE.application, params: { id: item.application_id } }"
        class="group flex h-full flex-col rounded-2xl bg-surface-soft p-4 transition hover:bg-white hover:shadow-[0_0.75rem_1.75rem_-0.875rem_rgb(20_20_30/0.3)] hover:ring-1 hover:ring-line"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-xs text-ink-secondary">{{ item.number }} · {{ formatRelativeTime(item.updated_at) }}</p>
            <p class="mt-0.5 truncate font-semibold text-ink">{{ item.product_name || item.product_code }}</p>
          </div>
          <BaseBadge :tone="STATUS[item.status].tone">{{ STATUS[item.status].label }}</BaseBadge>
        </div>
        <p class="mt-1 truncate text-sm text-ink-secondary">{{ item.company_name }}</p>
        <p class="mt-3 text-lg font-bold text-ink tabular-nums">
          {{ toAmount(item.amount) ? formatMoney(toAmount(item.amount)) : 'Сумма не выбрана' }}
        </p>
        <ol class="mt-4 flex items-center gap-1.5" :aria-label="`Этап: ${STATUS[item.status].label}`">
          <li v-for="(step, index) in TRACK" :key="step" class="flex-1">
            <span
              class="block h-1.5 rounded-full"
              :class="
                index < item.progress.done
                  ? item.progress.failed && index === item.progress.done - 1
                    ? 'bg-brand'
                    : 'bg-success'
                  : 'bg-surface-strong'
              "
            />
            <span class="mt-1 block truncate text-[10px] text-ink-secondary">{{ step }}</span>
          </li>
        </ol>
        <span class="mt-3 flex items-center gap-1 text-sm font-medium text-ink-secondary group-hover:text-brand">
          Открыть карточку
          <ChevronRight class="size-4" aria-hidden="true" />
        </span>
      </RouterLink>
    </li>
  </ul>
</template>
