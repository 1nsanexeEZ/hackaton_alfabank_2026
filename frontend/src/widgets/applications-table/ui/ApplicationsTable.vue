<script setup lang="ts">
import { AlarmClock } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'

import { ApplicationStatusBadge, isOverdue, RiskBadge } from '@/entities/application'
import { DEMO_CREDIT_PRODUCTS, findProduct } from '@/entities/credit-product'
import type { AdminApplication } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatDateTime, formatMoneyShort, formatRelativeTime, formatTerm } from '@/shared/lib'

/** Таблица заявок; на узких экранах превращается в список карточек */
withDefaults(defineProps<{ items: readonly AdminApplication[]; compact?: boolean }>(), { compact: false })

const productTitle = (id: string) => findProduct(DEMO_CREDIT_PRODUCTS, id).title
const link = (item: AdminApplication) => ({ name: ADMIN_ROUTE.application, params: { id: item.id } })
</script>

<template>
  <div>
    <table class="hidden w-full text-left text-sm md:table">
      <thead class="text-xs text-ink-secondary">
        <tr class="border-b border-line">
          <th scope="col" class="py-3 pr-4 pl-5 font-medium">Заявка</th>
          <th scope="col" class="px-4 py-3 font-medium">Клиент</th>
          <th v-if="!compact" scope="col" class="px-4 py-3 font-medium">Продукт</th>
          <th scope="col" class="px-4 py-3 text-right font-medium">Сумма</th>
          <th scope="col" class="px-4 py-3 font-medium">Скоринг</th>
          <th scope="col" class="px-4 py-3 font-medium">Статус</th>
          <th v-if="!compact" scope="col" class="py-3 pr-5 pl-4 font-medium">Ответственный</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id" class="group relative border-b border-line last:border-0 hover:bg-surface-soft">
          <td class="py-3 pr-4 pl-5 align-top">
            <RouterLink :to="link(item)" class="font-semibold text-ink after:absolute after:inset-0 after:content-['']">
              {{ item.number }}
            </RouterLink>
            <p class="mt-0.5 text-xs text-ink-secondary">{{ formatDateTime(item.createdAt) }}</p>
          </td>
          <td class="max-w-64 px-4 py-3 align-top">
            <p class="truncate font-medium text-ink">{{ item.applicantName }}</p>
            <p class="mt-0.5 text-xs text-ink-secondary tabular-nums">ИНН {{ item.inn }}</p>
          </td>
          <td v-if="!compact" class="px-4 py-3 align-top text-ink">{{ productTitle(item.productId) }}</td>
          <td class="px-4 py-3 text-right align-top whitespace-nowrap">
            <p class="font-semibold text-ink tabular-nums">{{ formatMoneyShort(item.amount) }}</p>
            <p class="mt-0.5 text-xs text-ink-secondary">{{ formatTerm(item.termMonths) }}</p>
          </td>
          <td class="px-4 py-3 align-top">
            <RiskBadge v-if="item.score" :score="item.score" />
            <span v-else class="text-xs text-ink-muted">ещё нет</span>
          </td>
          <td class="px-4 py-3 align-top">
            <ApplicationStatusBadge :status="item.status" />
            <p v-if="isOverdue(item)" class="mt-1 flex items-center gap-1 text-xs font-medium text-warning">
              <AlarmClock class="size-3.5" aria-hidden="true" />
              SLA {{ formatRelativeTime(item.dueAt) }}
            </p>
          </td>
          <td v-if="!compact" class="py-3 pr-5 pl-4 align-top text-ink-secondary">{{ item.assignee ?? '—' }}</td>
        </tr>
      </tbody>
    </table>

    <ul class="divide-y divide-line md:hidden">
      <li v-for="item in items" :key="item.id" class="relative px-5 py-4">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <RouterLink :to="link(item)" class="font-semibold text-ink after:absolute after:inset-0 after:content-['']">
              {{ item.number }}
            </RouterLink>
            <p class="truncate text-sm text-ink">{{ item.applicantName }}</p>
          </div>
          <ApplicationStatusBadge :status="item.status" />
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-secondary">
          <span class="font-semibold text-ink">{{ formatMoneyShort(item.amount) }}</span>
          <span>{{ productTitle(item.productId) }}</span>
          <RiskBadge v-if="item.score" :score="item.score" />
          <span v-if="isOverdue(item)" class="font-medium text-warning">просрочено</span>
        </div>
      </li>
    </ul>
  </div>
</template>
