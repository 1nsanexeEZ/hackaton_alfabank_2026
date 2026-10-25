<script setup lang="ts">
import type { Component } from 'vue'

/**
 * Сдержанная карточка-уведомление в стиле кабинета: белая плашка, иконка в мягком круге, подпись
 * и строка пояснения. Заполняет пустое место светлых секций лендинга вместо ярких наклеек (#257).
 * Только украшение — скрыта от скринридеров и не ловит клики; позицию задаёт родитель
 * (`absolute top-… right-…`). Только от xl: позиции рассчитаны на широкий экран, уже — наезжали бы на текст.
 */
type Tone = 'success' | 'info' | 'brand' | 'neutral'

withDefaults(
  defineProps<{
    title: string
    caption?: string
    /** Строка над заголовком, как «Решение по заявке» у уведомления в кабинете */
    eyebrow?: string
    icon?: Component
    tone?: Tone
    /** Сдвиг фазы покачивания, чтобы карточки не двигались синхронно */
    delay?: number
  }>(),
  { caption: undefined, eyebrow: undefined, icon: undefined, tone: 'info', delay: 0 },
)

const TONE_CLASS: Record<Tone, string> = {
  success: 'bg-success-soft text-success',
  info: 'bg-info-soft text-info',
  brand: 'bg-brand-soft text-brand',
  neutral: 'bg-surface text-ink-secondary',
}
</script>

<template>
  <div
    class="hint-card pointer-events-none hidden w-max max-w-72 items-start gap-3 rounded-2xl bg-white p-3.5 pr-5 shadow-[0_1.25rem_2.5rem_-1rem_rgb(20_20_30/0.25)] ring-1 ring-line select-none xl:flex"
    :style="{ animationDelay: `${-delay}s` }"
    aria-hidden="true"
  >
    <span v-if="icon" class="flex size-9 shrink-0 items-center justify-center rounded-full" :class="TONE_CLASS[tone]">
      <component :is="icon" class="size-[18px]" />
    </span>
    <span class="min-w-0">
      <span v-if="eyebrow" class="block text-xs text-ink-secondary">{{ eyebrow }}</span>
      <span class="block text-sm font-semibold text-ink">{{ title }}</span>
      <span v-if="caption" class="block text-xs text-ink-secondary">{{ caption }}</span>
    </span>
  </div>
</template>

<style scoped>
/* Как карточка решения у этапов: слегка покачивается на месте — без наклонов и вспышек */
.hint-card {
  animation: hint-float 6s ease-in-out infinite;
}

@keyframes hint-float {
  50% {
    translate: 0 -0.375rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hint-card {
    animation: none;
  }
}
</style>
