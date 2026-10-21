<script setup lang="ts">
/**
 * Фон из лент со знаком «А» (как в логотипе) под наклоном,
 * соседние ряды едут навстречу друг другу. Чисто декоративный слой для тёмных блоков:
 * родителю нужен `relative overflow-hidden`, контенту — `relative`, чтобы оказаться поверх.
 */

const ROWS = 24
</script>

<template>
  <div
    class="pattern-bg pointer-events-none absolute inset-0 overflow-hidden"
    aria-hidden="true"
  >
    <div class="pattern-bg__tilt">
      <div
        v-for="row in ROWS"
        :key="row"
        class="pattern-bg__row"
        :class="row % 2 ? 'is-left' : 'is-right'"
        :style="{ animationDuration: `${60 + (row % 5) * 12}s` }"
      />
    </div>
  </div>
</template>

<style scoped>
.pattern-bg {
  /* Знак «А» из AppLogo в плитке 48×48 с полями — шаг ленты */
  --glyph: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='-8 -6 48 44'%3E%3Cpath d='M16 7 9.5 23h3.2l1.3-3.4h4l1.3 3.4h3.2L16 7Zm-1.1 10.2L16 14l1.1 3.2h-2.2Z' fill='%23ef3124'/%3E%3Crect x='9.5' y='24.5' width='13' height='2' rx='1' fill='%23ef3124'/%3E%3C/svg%3E");
  --tile: 4.5rem;
}

.pattern-bg__tilt {
  position: absolute;
  inset: -50% -50%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.75rem;
  rotate: -12deg;
}

.pattern-bg__row {
  /* Запас в 10 плиток: ряд сдвигается ровно на них и бесшовно повторяется */
  width: calc(100% + var(--tile) * 10);
  height: var(--tile);
  flex: none;
  background: var(--glyph) repeat-x 0 0 / var(--tile) var(--tile);
  opacity: 0.15;
  animation: pattern-left linear infinite;
  will-change: transform;
}

.pattern-bg__row.is-right {
  opacity: 0.1;
  animation-name: pattern-right;
}

@keyframes pattern-left {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(calc(var(--tile) * -10));
  }
}

@keyframes pattern-right {
  from {
    transform: translateX(calc(var(--tile) * -10));
  }
  to {
    transform: translateX(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .pattern-bg__row {
    animation: none;
  }
}
</style>
