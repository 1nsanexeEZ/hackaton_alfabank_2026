<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Лист лендинга. Первый экран — нижний лист: остальная страница наезжает на него скруглённым краем
 * с тенью, а он отходит назад — чуть уменьшается и темнеет. Только sticky и анимация по прокрутке
 * (animation-timeline), без перехвата колеса и клавиш. Телефон, prefers-reduced-motion и браузеры
 * без animation-timeline — обычный поток со скруглением и тенью.
 */
defineProps<{
  /** Лист, который наезжает на первый экран; без флага — нижний лист */
  stacked?: boolean
}>()

const sheet = ref<HTMLElement | null>(null)
const height = ref(0)

// Высота нужна, чтобы первый экран выше окна прилипал низом к низу экрана и не прятал свою нижнюю часть
let observer: ResizeObserver | undefined
onMounted(() => {
  if (!sheet.value) return
  observer = new ResizeObserver(([entry]) => (height.value = entry?.borderBoxSize[0]?.blockSize ?? 0))
  observer.observe(sheet.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="sheet" class="sheet" :class="stacked ? 'sheet--stacked' : 'sheet--base'" :style="{ '--sheet-h': `${height}px` }">
    <slot />
  </div>
</template>

<style scoped>
/*
 * --r (скругление листа) и --stick (высота шапки) задаёт стопка в LandingPage.
 * Верхний лист заходит на нижний на --r, а нижний добирает --r своим фоном — под скруглением виден он сам.
 */
.sheet {
  position: relative;
}

.sheet--base {
  padding-bottom: var(--r);
}

.sheet--stacked {
  margin-top: calc(-1 * var(--r));
  overflow: clip;
  border-radius: var(--r) var(--r) 0 0;
  box-shadow: 0 -1.25rem 2.5rem -1.5rem rgb(18 18 19 / 0.35);
  view-timeline-name: --landing-stacked;
}

/* Затемнение отходящего листа: поверх содержимого, клики проходят насквозь */
.sheet--base::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  background: rgb(18 18 19);
  opacity: 0;
  pointer-events: none;
}

@supports (animation-timeline: view()) {
  @media (width >= 48rem) and (prefers-reduced-motion: no-preference) {
    .sheet--base {
      position: sticky;
      /* Невысокий первый экран прилипает под шапкой, высокий — когда его низ дошёл до низа окна */
      top: min(var(--stick), 100dvh - var(--sheet-h));
      /* Уменьшаем к середине видимой части листа */
      transform-origin: 50% calc(var(--sheet-h) - min(var(--sheet-h), 100dvh - var(--stick)) / 2);
      animation: sheet-recede linear both;
      animation-timeline: --landing-stacked;
      animation-range: entry 0% entry 100%;
    }

    .sheet--base::after {
      animation: sheet-dim linear both;
      animation-timeline: --landing-stacked;
      animation-range: entry 0% entry 100%;
    }
  }
}

@keyframes sheet-recede {
  to {
    transform: scale(0.96);
  }
}

@keyframes sheet-dim {
  to {
    opacity: 0.15;
  }
}
</style>
