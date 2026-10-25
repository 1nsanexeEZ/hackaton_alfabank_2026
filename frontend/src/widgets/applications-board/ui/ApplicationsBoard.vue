<script setup lang="ts">
import { ArrowDown, ArrowUp, Eye, EyeOff, RotateCcw, RefreshCw, SlidersHorizontal } from 'lucide-vue-next'
import { computed, ref, type Component } from 'vue'

import { AsyncState, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'

import { useBoardLayout, type ModuleId } from '../model/layout'
import { provideBoard, useBoardData, type Period } from '../model/useBoardData'
import AmountsModule from './modules/AmountsModule.vue'
import DecidedModule from './modules/DecidedModule.vue'
import FeedModule from './modules/FeedModule.vue'
import FlowModule from './modules/FlowModule.vue'
import FunnelModule from './modules/FunnelModule.vue'
import GradesModule from './modules/GradesModule.vue'
import KpiModule from './modules/KpiModule.vue'
import ProductsModule from './modules/ProductsModule.vue'
import QueueModule from './modules/QueueModule.vue'
import StatusesModule from './modules/StatusesModule.vue'

/**
 * Панель обзора: модули с графиками на общей сетке в три колонки. Каждый модуль — отдельный компонент,
 * данные берёт из панели (provide), поэтому модули можно скрывать и переставлять независимо.
 * Раскладка запоминается в браузере сотрудника.
 */
const data = useBoardData()
provideBoard(data)

const { modules, visible, hidden, toggle, move, reset } = useBoardLayout()

const COMPONENT: Record<ModuleId, Component> = {
  kpi: KpiModule,
  flow: FlowModule,
  decided: DecidedModule,
  funnel: FunnelModule,
  statuses: StatusesModule,
  queue: QueueModule,
  products: ProductsModule,
  amounts: AmountsModule,
  grades: GradesModule,
  feed: FeedModule,
}

/** Модули на метриках периода — остальные на списке заявок */
const ON_METRICS: readonly ModuleId[] = ['flow', 'decided']

const SPAN = { 1: '', 2: 'xl:col-span-2', 3: 'md:col-span-2 xl:col-span-3' } as const

const PERIODS: readonly { value: Period; label: string }[] = [
  { value: '7', label: '7 дней' },
  { value: '30', label: '30 дней' },
  { value: '90', label: '90 дней' },
]

const configuring = ref(false)

function stateOf(id: ModuleId) {
  if (ON_METRICS.includes(id)) return { loading: data.metricsLoading.value && !data.metrics.value, error: data.metrics.value ? null : data.metricsError.value }
  if (id === 'queue') return { loading: data.queueLoading.value && !data.queue.value, error: data.queue.value ? null : data.queueError.value }
  if (id === 'kpi') return { loading: data.applicationsLoading.value && !data.applications.value.length, error: data.applicationsError.value }
  return {
    loading: data.applicationsLoading.value && !data.applications.value.length,
    error: data.applications.value.length ? null : data.applicationsError.value,
  }
}

const empty = computed(() => !data.applicationsLoading.value && !data.applicationsError.value && !data.applications.value.length)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap items-center gap-3">
        <SegmentedControl v-model="data.period.value" :options="PERIODS" label="Период метрик" small />
        <span class="text-xs text-ink-secondary">период — для потока решений, автоматики и времени решения</span>
      </div>
      <div class="flex gap-2">
        <BaseButton variant="secondary" size="s" @click="data.reload">
          <RefreshCw class="size-4" aria-hidden="true" />
          Обновить
        </BaseButton>
        <BaseButton :variant="configuring ? 'primary' : 'secondary'" size="s" :aria-expanded="configuring" @click="configuring = !configuring">
          <SlidersHorizontal class="size-4" aria-hidden="true" />
          Настроить панель
        </BaseButton>
      </div>
    </div>

    <!-- Настройка раскладки: какие модули видны и в каком порядке -->
    <PanelCard v-if="configuring" title="Модули панели" description="Скройте лишнее и расставьте модули по порядку — раскладка сохранится в этом браузере">
      <template #actions>
        <BaseButton variant="ghost" size="s" @click="reset">
          <RotateCcw class="size-4" aria-hidden="true" />
          Как было
        </BaseButton>
      </template>
      <ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        <li
          v-for="(module, index) in modules"
          :key="module.id"
          class="flex items-center gap-2 rounded-xl px-3 py-2"
          :class="hidden.includes(module.id) ? 'bg-surface-soft text-ink-secondary' : 'bg-white ring-1 ring-line'"
        >
          <button
            type="button"
            class="flex size-9 shrink-0 items-center justify-center rounded-lg hover:bg-surface"
            :aria-label="hidden.includes(module.id) ? `Показать «${module.title}»` : `Скрыть «${module.title}»`"
            :aria-pressed="!hidden.includes(module.id)"
            @click="toggle(module.id)"
          >
            <EyeOff v-if="hidden.includes(module.id)" class="size-4" aria-hidden="true" />
            <Eye v-else class="size-4 text-brand" aria-hidden="true" />
          </button>
          <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ module.title }}</span>
          <button
            type="button"
            class="flex size-9 items-center justify-center rounded-lg hover:bg-surface disabled:opacity-30"
            :disabled="index === 0"
            :aria-label="`Поднять «${module.title}»`"
            @click="move(module.id, -1)"
          >
            <ArrowUp class="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="flex size-9 items-center justify-center rounded-lg hover:bg-surface disabled:opacity-30"
            :disabled="index === modules.length - 1"
            :aria-label="`Опустить «${module.title}»`"
            @click="move(module.id, 1)"
          >
            <ArrowDown class="size-4" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </PanelCard>

    <PanelCard v-if="empty">
      <p class="py-10 text-center text-sm text-ink-secondary">Заявок пока нет — графики появятся с первыми заявками</p>
    </PanelCard>

    <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <PanelCard v-for="module in visible" :key="module.id" :title="module.title" :description="module.description" :class="SPAN[module.span]">
        <AsyncState :loading="stateOf(module.id).loading" :error="stateOf(module.id).error" @retry="data.reload">
          <component :is="COMPONENT[module.id]" />
        </AsyncState>
      </PanelCard>
      <PanelCard v-if="!visible.length" class="md:col-span-2 xl:col-span-3">
        <p class="py-8 text-center text-sm text-ink-secondary">Все модули скрыты — включите нужные в «Настроить панель»</p>
      </PanelCard>
    </div>
  </div>
</template>
