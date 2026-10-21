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
        'shrink-0 rounded-full font-medium transition-colors',
        small ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm sm:px-5',
        model === option.value ? 'bg-white text-ink shadow-sm' : 'text-ink-secondary hover:text-ink',
      ]"
      @click="model = option.value"
    >
      {{ option.label }}
    </button>
  </div>
</template>
