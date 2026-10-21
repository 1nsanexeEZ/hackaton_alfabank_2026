<script setup lang="ts">
import { AlarmClock, CircleCheck, Clock, Inbox, Wallet } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { RISK_CLASS_META } from '@/entities/application'
import type { DashboardStats, RiskClass } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatMoneyShort, formatPercent, pluralize } from '@/shared/lib'
import { PanelCard } from '@/shared/ui'

import BarList from './BarList.vue'
import DailyColumns from './DailyColumns.vue'

const props = defineProps<{ stats: DashboardStats }>()

const tiles = computed(() => [
  {
    label: 'В работе',
    value: String(props.stats.inProgress),
    note: props.stats.overdue ? `${props.stats.overdue} просрочено по SLA` : 'просрочек нет',
    warn: props.stats.overdue > 0,
    icon: Inbox,
  },
  {
    label: 'Доля одобрений',
    value: formatPercent(props.stats.approvalRate * 100),
    note: `из ${props.stats.decided} ${pluralize(props.stats.decided, ['решения', 'решений', 'решений'])}`,
    warn: false,
    icon: CircleCheck,
  },
  {
    label: 'Одобрено',
    value: formatMoneyShort(props.stats.approvedVolume),
    note: `средняя заявка ${formatMoneyShort(props.stats.averageAmount)}`,
    warn: false,
    icon: Wallet,
  },
  {
    label: 'Время решения',
    value: `${props.stats.averageDecisionHours.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} ч`,
    note: 'в среднем от подачи',
    warn: false,
    icon: Clock,
  },
])

const funnel = computed(() => {
  const first = props.stats.funnel[0]?.count || 1
  return props.stats.funnel.map((step) => ({
    key: step.label,
    label: step.label,
    value: step.count,
    caption: `${step.count} · ${Math.round((step.count / first) * 100)}%`,
  }))
})

const products = computed(() =>
  props.stats.byProduct.map((item) => ({
    key: item.productId,
    label: item.title,
    value: item.count,
    caption: `${item.count} · ${formatMoneyShort(item.amount)}`,
  })),
)

const risks = computed(() =>
  (Object.keys(props.stats.byRisk) as RiskClass[]).map((risk) => ({
    key: risk,
    label: `${risk} · ${RISK_CLASS_META[risk].label.toLowerCase()}`,
    value: props.stats.byRisk[risk],
    color: RISK_CLASS_META[risk].color,
  })),
)
</script>

<template>
  <div class="space-y-6">
    <ul class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <li v-for="tile in tiles" :key="tile.label" class="rounded-2xl bg-white p-5 ring-1 ring-line">
        <p class="flex items-center gap-2 text-sm text-ink-secondary">
          <component :is="tile.icon" class="size-4" aria-hidden="true" />
          {{ tile.label }}
        </p>
        <p class="mt-2 text-3xl font-semibold tracking-tight text-ink">{{ tile.value }}</p>
        <p class="mt-1 flex items-center gap-1.5 text-sm" :class="tile.warn ? 'font-medium text-warning' : 'text-ink-secondary'">
          <AlarmClock v-if="tile.warn" class="size-4" aria-hidden="true" />
          {{ tile.note }}
        </p>
      </li>
    </ul>

    <div class="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
      <PanelCard title="Заявки по дням" description="Последние 14 дней">
        <DailyColumns :days="stats.daily" />
      </PanelCard>
      <PanelCard title="Воронка" description="Сколько заявок дошло до каждого шага">
        <BarList :items="funnel" />
      </PanelCard>
    </div>

    <div class="grid gap-6 lg:grid-cols-2">
      <PanelCard title="По продуктам" description="Количество и сумма заявок">
        <template #actions>
          <RouterLink :to="{ name: ADMIN_ROUTE.products }" class="text-sm font-medium text-info hover:underline">Продукты</RouterLink>
        </template>
        <BarList :items="products" />
      </PanelCard>
      <PanelCard title="Классы риска" description="По заявкам, прошедшим скоринг">
        <template #actions>
          <RouterLink :to="{ name: ADMIN_ROUTE.scoring }" class="text-sm font-medium text-info hover:underline">Настройки</RouterLink>
        </template>
        <BarList :items="risks" />
      </PanelCard>
    </div>
  </div>
</template>
