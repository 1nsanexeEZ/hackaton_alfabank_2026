<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{ label: string; description?: string; disabled?: boolean }>(), {
  description: undefined,
  disabled: false,
})

const model = defineModel<boolean>({ required: true })

const id = useId()
</script>

<template>
  <div class="flex items-start justify-between gap-4">
    <label :for="id" class="cursor-pointer text-sm">
      <span class="block font-medium text-ink">{{ label }}</span>
      <span v-if="description" class="mt-0.5 block text-ink-secondary">{{ description }}</span>
    </label>
    <button
      :id="id"
      type="button"
      role="switch"
      :aria-checked="model"
      :disabled="disabled"
      :class="[
        'relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        model ? 'bg-brand' : 'bg-surface-strong',
      ]"
      @click="model = !model"
    >
      <span
        class="absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform"
        :class="model && 'translate-x-5'"
      />
    </button>
  </div>
</template>
