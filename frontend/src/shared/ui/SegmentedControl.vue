<script setup lang="ts" generic="T extends string">
withDefaults(
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
</script>

<template>
  <div
    role="group"
    :aria-label="label"
    class="inline-flex max-w-full gap-1 overflow-x-auto rounded-full bg-surface p-1 [scrollbar-width:none]"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :aria-pressed="model === option.value"
      :class="[
        'segmented__option shrink-0 rounded-full font-medium',
        small ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm sm:px-5',
        model === option.value ? 'is-on bg-white text-ink shadow-sm' : 'text-ink-secondary hover:text-ink',
      ]"
      @click="model = option.value"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
/* Варианты приподнимаются при наведении, выбранный выпрыгивает с пружиной */
.segmented__option {
  transition:
    color 0.25s,
    background-color 0.25s,
    translate 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.segmented__option:hover:not(.is-on) {
  translate: 0 -2px;
}

.segmented__option.is-on {
  animation: segmented-pop 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.segmented__option:active {
  scale: 0.94;
}

@keyframes segmented-pop {
  from {
    scale: 0.85;
  }
}

@media (prefers-reduced-motion: reduce) {
  .segmented__option {
    animation: none !important;
  }
}
</style>
