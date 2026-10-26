<script setup lang="ts" generic="T extends string">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    options: readonly { value: T; label: string }[]
    /** Подпись группы для скринридеров */
    label: string
    /** Компактный вариант — для строк настроек */
    small?: boolean
  }>(),
  { small: false },
)

const model = defineModel<T>({ required: true })

/*
 * Как переключатель в настройках телефона: под выбранным вариантом лежит ползунок, при выборе другого
 * он переезжает под него. Положение и ширину берём из самой кнопки. Цвет ползунка — --segmented-thumb:
 * на сайте фирменный красный, в рабочем месте банка тёмный (красный там — только у главного действия).
 */
const buttons = ref<HTMLButtonElement[]>([])
const thumb = ref({ x: 0, width: 0 })
// Первое измерение — без анимации, иначе ползунок выезжает из левого края при загрузке
const ready = ref(false)

function measure() {
  const index = props.options.findIndex((option) => option.value === model.value)
  const button = buttons.value[index]
  thumb.value = button ? { x: button.offsetLeft, width: button.offsetWidth } : { x: 0, width: 0 }
}

let resizeObserver: ResizeObserver | undefined

onMounted(async () => {
  measure()
  await nextTick()
  requestAnimationFrame(() => (ready.value = true))
  if ('ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(measure)
    buttons.value.forEach((button) => resizeObserver?.observe(button))
  }
})

onBeforeUnmount(() => resizeObserver?.disconnect())

watch([model, () => props.options], () => nextTick(measure))
</script>

<template>
  <div
    role="group"
    :aria-label="label"
    class="segmented relative isolate inline-flex max-w-full gap-1 overflow-x-auto rounded-full bg-surface p-1 [scrollbar-width:none]"
  >
    <span
      class="segmented__thumb pointer-events-none absolute top-1 bottom-1 left-0 -z-10 rounded-full bg-(--segmented-thumb,var(--color-brand)) shadow-sm"
      :class="{ 'is-ready': ready }"
      :style="{ width: `${thumb.width}px`, translate: `${thumb.x}px 0`, opacity: thumb.width ? 1 : 0 }"
      aria-hidden="true"
    />
    <button
      v-for="option in options"
      :key="option.value"
      ref="buttons"
      type="button"
      :aria-pressed="model === option.value"
      :class="[
        'segmented__option shrink-0 rounded-full font-medium',
        small ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm sm:px-5',
        model === option.value ? 'text-white' : 'text-ink-secondary hover:text-ink',
      ]"
      @click="model = option.value"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented__option {
  transition: color 0.3s;
}

.segmented__thumb.is-ready {
  transition:
    translate 0.4s cubic-bezier(0.32, 0.72, 0, 1),
    width 0.4s cubic-bezier(0.32, 0.72, 0, 1),
    scale 0.2s ease;
}

/* Пока палец на переключателе, ползунок чуть поджимается — как на телефоне */
.segmented:active .segmented__thumb {
  scale: 0.96;
}

@media (prefers-reduced-motion: reduce) {
  .segmented__thumb.is-ready {
    transition: none;
  }
}
</style>
