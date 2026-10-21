<script setup lang="ts" generic="T extends string">
import { ChevronDown } from 'lucide-vue-next'
import { useId } from 'vue'

withDefaults(
  defineProps<{
    label: string
    options: readonly { value: T; label: string }[]
    /** Компактная высота — для фильтров и форм админки */
    dense?: boolean
    /** Подпись только для скринридеров */
    hideLabel?: boolean
  }>(),
  { dense: false, hideLabel: false },
)

const model = defineModel<T>({ required: true })

const id = useId()
</script>

<template>
  <div>
    <label :for="id" class="mb-2 block text-sm font-medium text-ink" :class="hideLabel && 'sr-only'">{{ label }}</label>
    <div class="relative">
      <select
        :id="id"
        v-model="model"
        :class="[
          'w-full cursor-pointer appearance-none bg-surface pr-12 pl-4 text-ink transition outline-none focus:bg-white focus:ring-2 focus:ring-ink/20',
          dense ? 'h-11 rounded-lg text-sm' : 'h-14 rounded-xl text-base',
        ]"
      >
        <option v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
      <ChevronDown
        class="pointer-events-none absolute top-1/2 right-4 size-5 -translate-y-1/2 text-ink-secondary"
        aria-hidden="true"
      />
    </div>
  </div>
</template>
