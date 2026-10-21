<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Фон из лент со знаком «А» (как в логотипе) под наклоном,
 * соседние ряды едут навстречу друг другу. Чисто декоративный слой для тёмных блоков:
 * родителю нужен `relative overflow-hidden`, контенту — `relative`, чтобы оказаться поверх.
 *
 * Производительность: все ряды нарисованы двумя слоями (чётные и нечётные) вместо
 * отдельного элемента на ряд, анимируется только transform, а когда блок
 * вне экрана, анимация стоит на паузе.
 */
const root = ref<HTMLElement>()
const paused = ref(true)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (!('IntersectionObserver' in window)) {
    paused.value = false
    return
  }
  observer = new IntersectionObserver(([entry]) => {
    paused.value = !entry?.isIntersecting
  })
  if (root.value) observer.observe(root.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div
    ref="root"
    class="pattern-bg pointer-events-none absolute inset-0 overflow-hidden"
    :class="{ 'is-paused': paused }"
    aria-hidden="true"
  >
    <div class="pattern-bg__tilt">
      <div class="pattern-bg__layer is-left" />
      <div class="pattern-bg__layer is-right" />
    </div>
  </div>
</template>

<style scoped>
.pattern-bg {
  /*
   * Плитка на два ряда: знак «А» в верхней половине, нижняя пустая.
   * Второй слой сдвинут на один ряд вниз — так ряды чередуются.
   */
  --glyph: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 112'%3E%3Cg transform='translate(8 6)' fill='%23ef3124'%3E%3Cpath d='M16 7 9.5 23h3.2l1.3-3.4h4l1.3 3.4h3.2L16 7Zm-1.1 10.2L16 14l1.1 3.2h-2.2Z'/%3E%3Crect x='9.5' y='24.5' width='13' height='2' rx='1'/%3E%3C/g%3E%3C/svg%3E");
  --tile: 4.5rem;
  /* Шаг ряда: высота знака + зазор; плитка — два ряда */
  --row: 5.25rem;
}

.pattern-bg__tilt {
  position: absolute;
  inset: -50%;
  rotate: -12deg;
}

.pattern-bg__layer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  /* Запас в 10 плиток: слой сдвигается ровно на них и бесшовно повторяется */
  width: calc(100% + var(--tile) * 10);
  background: var(--glyph) repeat 0 0 / var(--tile) calc(var(--row) * 2);
  animation: pattern-left 70s linear infinite;
}

.pattern-bg__layer.is-left {
  opacity: 0.15;
}

.pattern-bg__layer.is-right {
  opacity: 0.1;
  background-position: 0 var(--row);
  animation-name: pattern-right;
  animation-duration: 90s;
}

.is-paused .pattern-bg__layer {
  animation-play-state: paused;
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
  .pattern-bg__layer {
    animation: none;
  }
}
</style>
