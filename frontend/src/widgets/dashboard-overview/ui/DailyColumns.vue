<script setup lang="ts">
import { computed, ref } from 'vue'

import { pluralize } from '@/shared/lib'

/** Заявки по дням: одна серия столбцов, подсказка при наведении, таблица для скринридеров */
const props = defineProps<{ days: readonly { date: string; count: number }[] }>()

const HEIGHT = 160
const active = ref<number | null>(null)

const max = computed(() => Math.max(4, ...props.days.map((day) => day.count)))
// Чистые деления оси: 0, половина, максимум
const ticks = computed(() => {
  const top = Math.ceil(max.value / 2) * 2
  return [top, top / 2, 0]
})

const dayLabel = (date: string) => new Date(date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
const weekday = (date: string) => new Date(date).toLocaleDateString('ru-RU', { weekday: 'short' })
const APPLICATION_FORMS = ['заявка', 'заявки', 'заявок'] as const
</script>

<template>
  <div class="relative">
    <div class="flex gap-3">
      <div class="flex flex-col justify-between pb-6 text-right text-xs text-ink-muted tabular-nums" :style="{ height: `${HEIGHT + 24}px` }" aria-hidden="true">
        <span v-for="tick in ticks" :key="tick" class="-translate-y-1.5 leading-none">{{ tick }}</span>
      </div>
      <div class="relative min-w-0 flex-1">
        <div class="pointer-events-none absolute inset-x-0 top-0 flex flex-col justify-between" :style="{ height: `${HEIGHT}px` }" aria-hidden="true">
          <span v-for="tick in ticks" :key="tick" class="h-px bg-line" />
        </div>
        <ul class="relative flex items-end" :style="{ height: `${HEIGHT}px` }" aria-hidden="true">
          <li
            v-for="(day, index) in days"
            :key="day.date"
            class="relative flex h-full flex-1 cursor-default items-end justify-center"
            @mouseenter="active = index"
            @mouseleave="active = null"
          >
            <span
              class="w-full max-w-6 rounded-t transition-opacity"
              :class="[active !== null && active !== index && 'opacity-40', day.count === 0 && 'h-0.5 bg-surface-strong']"
              :style="day.count ? { height: `${(day.count / ticks[0]!) * HEIGHT}px`, background: 'var(--color-info)' } : undefined"
            />
            <span
              v-if="active === index"
              class="absolute bottom-full z-10 mb-2 rounded-lg bg-night px-2.5 py-1.5 text-xs whitespace-nowrap text-on-night shadow-lg"
              :style="{ bottom: `${(day.count / ticks[0]!) * HEIGHT}px` }"
            >
              {{ dayLabel(day.date) }}, {{ weekday(day.date) }} ·
              <b class="font-semibold">{{ day.count }} {{ pluralize(day.count, APPLICATION_FORMS) }}</b>
            </span>
          </li>
        </ul>
        <div class="mt-2 flex text-[11px] text-ink-muted" aria-hidden="true">
          <span v-for="(day, index) in days" :key="day.date" class="flex-1 text-center">
            {{ index % 2 === 1 || index === days.length - 1 ? new Date(day.date).getDate() : '' }}
          </span>
        </div>
      </div>
    </div>

    <table class="sr-only">
      <caption>Заявки по дням</caption>
      <tr v-for="day in days" :key="day.date">
        <th scope="row">{{ dayLabel(day.date) }}</th>
        <td>{{ day.count }}</td>
      </tr>
    </table>
  </div>
</template>
