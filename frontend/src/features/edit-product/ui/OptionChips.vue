<script setup lang="ts" generic="T extends string">
import { Check } from 'lucide-vue-next'

/** Несколько значений из списка — чипы-переключатели; порядок выбора сохраняется */
defineProps<{
  label: string
  options: readonly { value: T; label: string }[]
  error?: string
  disabled?: boolean
}>()
const model = defineModel<T[]>({ required: true })

function toggle(value: T) {
  model.value = model.value.includes(value) ? model.value.filter((item) => item !== value) : [...model.value, value]
}
</script>

<template>
  <fieldset :disabled="disabled" class="min-w-0">
    <legend class="mb-2 text-sm font-medium text-ink">{{ label }}</legend>
    <div class="flex flex-wrap gap-2">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        :aria-pressed="model.includes(option.value)"
        :class="[
          'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm ring-1 transition disabled:opacity-60',
          model.includes(option.value) ? 'bg-ink text-white ring-ink' : 'bg-white text-ink ring-line hover:ring-ink/25',
        ]"
        @click="toggle(option.value)"
      >
        <Check v-if="model.includes(option.value)" class="size-3.5" :stroke-width="3" aria-hidden="true" />
        {{ option.label }}
      </button>
    </div>
    <p v-if="error" class="mt-1.5 text-xs text-brand" role="alert">{{ error }}</p>
  </fieldset>
</template>
