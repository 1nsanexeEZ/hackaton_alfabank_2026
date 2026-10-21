<script setup lang="ts">
import type { Component } from 'vue'

/**
 * Декоративный «стикер» для светлых секций: яркая наклейка с иконкой
 * или звезда-бейдж. Только украшение — скрыт от скринридеров и не ловит клики.
 * Позицию задаёт родитель классами (`absolute top-… right-…`), на мобильных стикеры скрыты.
 */
type Tone = 'brand' | 'sun' | 'sky' | 'mint'

withDefaults(
  defineProps<{
    title: string
    caption?: string
    icon?: Component
    tone?: Tone
    /** Наклон в градусах */
    tilt?: number
    /** Звезда-бейдж вместо наклейки */
    burst?: boolean
    /** Сдвиг фазы покачивания, чтобы стикеры не двигались синхронно */
    delay?: number
  }>(),
  { caption: undefined, icon: undefined, tone: 'brand', tilt: -6, burst: false, delay: 0 },
)
</script>

<template>
  <div
    class="sticker pointer-events-none hidden select-none lg:block"
    :class="`is-${tone}`"
    :style="{ rotate: `${tilt}deg`, animationDelay: `${-delay}s` }"
    aria-hidden="true"
  >
    <div v-if="burst" class="sticker__burst">
      <span class="sticker__burst-shape" />
      <span class="relative flex flex-col items-center leading-none">
        <span v-if="caption" class="text-[0.6875rem] font-bold tracking-wider uppercase">{{ caption }}</span>
        <span class="mt-1 text-lg font-extrabold">{{ title }}</span>
      </span>
    </div>

    <div v-else class="sticker__card flex items-center gap-3">
      <span v-if="icon" class="sticker__icon flex size-11 shrink-0 items-center justify-center rounded-full">
        <component :is="icon" class="size-5" :stroke-width="2.5" />
      </span>
      <span class="leading-tight whitespace-nowrap">
        <span class="block text-base font-extrabold">{{ title }}</span>
        <span v-if="caption" class="sticker__caption block text-xs font-medium">{{ caption }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
/* Палитра наклеек: фон, текст, иконка */
.sticker.is-brand {
  --bg: var(--color-brand);
  --fg: white;
  --icon-bg: white;
  --icon-fg: var(--color-brand);
}

.sticker.is-sun {
  --bg: #ffd03d;
  --fg: #3a2a00;
  --icon-bg: #3a2a00;
  --icon-fg: #ffd03d;
}

.sticker.is-sky {
  --bg: #4d8dff;
  --fg: white;
  --icon-bg: white;
  --icon-fg: #4d8dff;
}

.sticker.is-mint {
  --bg: #2ec98f;
  --fg: white;
  --icon-bg: white;
  --icon-fg: #1c9a6b;
}

.sticker {
  animation: sticker-wobble 6s ease-in-out infinite;
}

.sticker__card {
  padding: 0.625rem 1.25rem 0.625rem 0.625rem;
  border-radius: 999px;
  background: var(--bg);
  color: var(--fg);
  /* Толстая белая кромка и тень — как у вырезанной наклейки */
  box-shadow:
    0 0 0 5px white,
    0 14px 30px rgb(30 43 68 / 0.18);
}

.sticker__icon {
  background: var(--icon-bg);
  color: var(--icon-fg);
}

.sticker__caption {
  opacity: 0.85;
}

/* Звезда-бейдж: зубчатый круг, медленно вращается */
.sticker__burst {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 9.5rem;
  height: 9.5rem;
  color: var(--fg);
  text-align: center;
}

.sticker__burst-shape {
  position: absolute;
  inset: 0;
  background: var(--bg);
  filter: drop-shadow(0 0 0 white) drop-shadow(0 12px 24px rgb(30 43 68 / 0.18));
  clip-path: polygon(
    50% 0%, 59% 9%, 71% 4%, 75% 16%, 88% 16%, 87% 29%, 98% 35%, 92% 47%,
    100% 57%, 90% 65%, 93% 78%, 80% 80%, 77% 93%, 65% 90%, 56% 100%, 47% 92%,
    35% 98%, 29% 87%, 16% 88%, 16% 75%, 4% 71%, 9% 59%, 0% 50%, 8% 40%,
    3% 28%, 15% 23%, 15% 10%, 28% 11%, 33% 1%, 44% 7%
  );
  animation: sticker-spin 24s linear infinite;
}

@keyframes sticker-wobble {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  30% {
    transform: translateY(-8px) rotate(3deg);
  }
  60% {
    transform: translateY(-3px) rotate(-2deg);
  }
}

@keyframes sticker-spin {
  to {
    rotate: 360deg;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sticker,
  .sticker__burst-shape {
    animation: none;
  }
}
</style>
