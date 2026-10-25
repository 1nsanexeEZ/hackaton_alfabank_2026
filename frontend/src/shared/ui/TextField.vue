<script setup lang="ts">
import { computed, useId } from 'vue'

import { inputModeFor, sanitizeInput, type InputFilter } from '../lib/input'

const props = withDefaults(
  defineProps<{
    label: string
    placeholder?: string
    hint?: string
    error?: string
    type?: 'text' | 'email' | 'password' | 'tel' | 'search' | 'date'
    inputmode?: 'text' | 'numeric' | 'decimal' | 'email' | 'tel'
    autocomplete?: string
    maxlength?: number
    /** Компактная высота — для таблиц и форм админки */
    dense?: boolean
    /** Что можно вводить: digits — только цифры, decimal — число с запятой, amount — сумма с разделителями тысяч */
    filter?: InputFilter
    required?: boolean
  }>(),
  {
    placeholder: undefined,
    hint: undefined,
    error: undefined,
    type: 'text',
    inputmode: 'text',
    autocomplete: 'off',
    maxlength: undefined,
    dense: false,
    filter: undefined,
    required: false,
  },
)

const model = defineModel<string>({ required: true })

const id = useId()
const describedBy = computed(() => (props.error || props.hint ? `${id}-description` : undefined))
const mode = computed(() => (props.filter ? inputModeFor(props.filter) : props.inputmode))

/** Недопустимый символ не попадает ни в модель, ни в поле: возвращаем очищенное значение и в DOM */
function onInput(event: Event) {
  const input = event.target as HTMLInputElement
  const next = props.filter ? sanitizeInput(input.value, props.filter) : input.value
  if (next !== input.value) input.value = next
  model.value = next
}
</script>

<template>
  <div>
    <label :for="id" class="mb-2 block text-sm font-medium text-ink">{{ label }}</label>
    <input
      :id="id"
      :value="model"
      :type="type"
      :placeholder="placeholder"
      :inputmode="mode"
      :autocomplete="autocomplete"
      :maxlength="maxlength"
      :required="required"
      :aria-invalid="Boolean(error)"
      :aria-describedby="describedBy"
      @input="onInput"
      :class="[
        'w-full bg-surface px-4 text-base text-ink transition outline-none placeholder:text-ink-muted',
        'focus:bg-white focus:ring-2 focus:ring-ink/20',
        dense ? 'h-11 rounded-lg text-sm' : 'h-14 rounded-xl',
        error && 'bg-brand-soft ring-1 ring-brand focus:ring-brand',
      ]"
    />
    <p v-if="error" :id="describedBy" class="mt-1.5 text-sm text-brand">{{ error }}</p>
    <p v-else-if="hint" :id="describedBy" class="mt-1.5 text-sm text-ink-secondary">{{ hint }}</p>
  </div>
</template>
