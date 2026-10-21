<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    placeholder?: string
    hint?: string
    error?: string
    inputmode?: 'text' | 'numeric' | 'decimal' | 'email' | 'tel'
    autocomplete?: string
    maxlength?: number
  }>(),
  {
    placeholder: undefined,
    hint: undefined,
    error: undefined,
    inputmode: 'text',
    autocomplete: 'off',
    maxlength: undefined,
  },
)

const model = defineModel<string>({ required: true })

const id = useId()
const describedBy = computed(() => (props.error || props.hint ? `${id}-description` : undefined))
</script>

<template>
  <div>
    <label :for="id" class="mb-2 block text-sm font-medium text-ink">{{ label }}</label>
    <input
      :id="id"
      v-model="model"
      type="text"
      :placeholder="placeholder"
      :inputmode="inputmode"
      :autocomplete="autocomplete"
      :maxlength="maxlength"
      :aria-invalid="Boolean(error)"
      :aria-describedby="describedBy"
      :class="[
        'h-14 w-full rounded-xl bg-surface px-4 text-base text-ink transition outline-none placeholder:text-ink-muted',
        'focus:bg-white focus:ring-2 focus:ring-ink/20',
        error && 'bg-brand-soft ring-1 ring-brand focus:ring-brand',
      ]"
    />
    <p v-if="error" :id="describedBy" class="mt-1.5 text-sm text-brand">{{ error }}</p>
    <p v-else-if="hint" :id="describedBy" class="mt-1.5 text-sm text-ink-secondary">{{ hint }}</p>
  </div>
</template>
