<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { useProductCatalog } from '@/entities/credit-product'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatMoney, formatRelativeTime, formatTerm } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

import { STATUS, TRACK, trackProgress } from '../../model/status'
import { amountOf, useBoard } from '../../model/useBoardData'

const SHOWN = 6

const { applications, companies, loadCompanies } = useBoard()
const { products } = useProductCatalog()

/** Последние изменённые заявки — карточками с трекером этапов, как в кабинете клиента */
const items = computed(() =>
  [...applications.value]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, SHOWN)
    .map((item) => ({ ...item, progress: trackProgress(item.status) })),
)
watch(items, (list) => loadCompanies(list.map((item) => item.organization_id)), { immediate: true })

const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code
</script>

<template>
  <ul class="grid gap-3 md:grid-cols-2">
    <li v-for="item in items" :key="item.id">
      <RouterLink
        :to="{ name: ADMIN_ROUTE.application, params: { id: item.id } }"
        class="group flex h-full flex-col rounded-2xl bg-surface-soft p-4 transition hover:bg-white hover:shadow-[0_0.75rem_1.75rem_-0.875rem_rgb(20_20_30/0.3)] hover:ring-1 hover:ring-line"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-xs text-ink-secondary">{{ item.number }} · {{ formatRelativeTime(item.updated_at) }}</p>
            <p class="mt-0.5 truncate font-semibold text-ink">{{ productTitle(item.product_code) }}</p>
          </div>
          <BaseBadge :tone="STATUS[item.status].tone">{{ STATUS[item.status].label }}</BaseBadge>
        </div>
        <p class="mt-1 truncate text-sm text-ink-secondary">{{ companies[item.organization_id]?.name ?? 'Компания…' }}</p>
        <p class="mt-3 text-lg font-bold text-ink tabular-nums">
          {{ amountOf(item) ? formatMoney(amountOf(item)) : 'Сумма не выбрана' }}
          <span v-if="item.term_months" class="text-sm font-normal text-ink-secondary">на {{ formatTerm(item.term_months) }}</span>
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
