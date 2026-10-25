<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * Число, которое при изменении «перебирается»: цифры хаотично растут от 1 и встают на новое значение.
 * Скринридер слышит только итог, при prefers-reduced-motion анимации нет.
 */
const props = withDefaults(
  defineProps<{
    value: number
    format?: (value: number) => string
    /** Длительность перебора, мс */
    duration?: number
    /** Перебирать и при первом показе, а не только при изменении */
    animateOnMount?: boolean
  }>(),
  { format: (value: number) => String(value), duration: 700, animateOnMount: false },
)

const shown = ref(props.animateOnMount ? 1 : props.value)
let frame = 0

/** Сколько знаков после запятой у итога: промежуточные значения показываем так же */
function decimalsOf(value: number): number {
  if (Number.isInteger(value)) return 0
  return Math.min((String(value).split('.')[1] ?? '').length, 2)
}

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function run(target: number) {
  cancelAnimationFrame(frame)
  if (reducedMotion() || !Number.isFinite(target) || target <= 1) {
    shown.value = target
    return
  }
  const decimals = decimalsOf(target)
  const factor = 10 ** decimals
  const start = performance.now()
  const step = (now: number) => {
    const progress = Math.min((now - start) / props.duration, 1)
    if (progress >= 1) {
      shown.value = target
      return
    }
    // растём от 1 к цели с замедлением, а шум, затухающий к концу, даёт «хаотичный» перебор цифр
    const eased = 1 - (1 - progress) ** 3
    const noise = (Math.random() - 0.5) * target * 0.6 * (1 - progress)
    const next = Math.min(Math.max(1 + (target - 1) * eased + noise, 1), target)
    shown.value = Math.round(next * factor) / factor
    frame = requestAnimationFrame(step)
  }
  frame = requestAnimationFrame(step)
}

watch(
  () => props.value,
  (target, previous) => {
    if (target !== previous) run(target)
  },
)
if (props.animateOnMount) run(props.value)

onBeforeUnmount(() => cancelAnimationFrame(frame))

const text = computed(() => props.format(shown.value))
const finalText = computed(() => props.format(props.value))
</script>

<template>
  <span class="tabular-nums"><span aria-hidden="true">{{ text }}</span><span class="sr-only">{{ finalText }}</span></span>
</template>
