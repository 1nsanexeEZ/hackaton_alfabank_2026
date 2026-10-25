<script setup lang="ts">
import type { Component } from 'vue'

/**
 * Карточка-фрагмент интерфейса для светлых секций лендинга: как уведомление в кабинете —
 * иконка, короткая подпись, главный факт и строка пояснения. Только украшение: скрыта от скринридеров,
 * не ловит клики, на мобильных не показывается. Позицию задаёт родитель (`absolute top-… right-…`).
 */
type Tone = 'success' | 'brand' | 'neutral'

withDefaults(
  defineProps<{
    icon: Component
    /** Мелкая подпись сверху, например «Решение по заявке» */
    eyebrow: string
    title: string
    text?: string
    /** Мелкая пометка справа от подписи, например «только что» */
    meta?: string
    tone?: Tone
    /** Сдвиг фазы покачивания, чтобы карточки не двигались синхронно */
    delay?: number
  }>(),
  { text: undefined, meta: undefined, tone: 'success', delay: 0 },
)

const ICON_TONE: Record<Tone, string> = {
  success: 'bg-success-soft text-success',
  brand: 'bg-brand-soft text-brand',
  neutral: 'bg-surface text-ink-secondary',
}
</script>

<template>
  <div
    class="float-card pointer-events-none hidden w-80 items-start gap-3 rounded-2xl bg-white p-4 shadow-[0_1.25rem_2.5rem_-1rem_rgb(20_20_30/0.25)] ring-1 ring-line select-none lg:flex"
    :style="{ animationDelay: `${-delay}s` }"
    aria-hidden="true"
  >
    <span class="flex size-10 shrink-0 items-center justify-center rounded-full" :class="ICON_TONE[tone]">
      <component :is="icon" class="size-5" />
    </span>
    <div class="min-w-0 flex-1">
      <p class="flex items-center justify-between gap-2 text-xs text-ink-secondary">
        {{ eyebrow }}
        <span v-if="meta" class="shrink-0">{{ meta }}</span>
      </p>
      <p class="mt-0.5 font-semibold text-ink">{{ title }}</p>
      <p v-if="text" class="mt-0.5 text-sm text-ink-secondary">{{ text }}</p>
    </div>
  </div>
</template>

<style scoped>
/* Слегка покачивается на месте — без наклонов и вспышек */
.float-card {
  animation: float-card 6s ease-in-out infinite;
}

@keyframes float-card {
  50% {
    translate: 0 -0.375rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .float-card {
    animation: none;
  }
}
</style>
