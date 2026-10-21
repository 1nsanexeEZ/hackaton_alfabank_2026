<script setup lang="ts">
import { computed, ref, useId } from 'vue'

import { clamp, onlyDigits } from '../lib'

const props = withDefaults(
  defineProps<{
    label: string
    min: number
    max: number
    step?: number
    formatValue?: (value: number) => string
    /** Разрешить ввод числа с клавиатуры */
    editable?: boolean
  }>(),
  { step: 1, formatValue: (value: number) => String(value), editable: true },
)

const model = defineModel<number>({ required: true })

const id = useId()
const isFocused = ref(false)
const draft = ref('')

const progress = computed(() => {
  const span = props.max - props.min
  return span > 0 ? ((model.value - props.min) / span) * 100 : 0
})

const displayValue = computed(() => (isFocused.value ? draft.value : props.formatValue(model.value)))

function onFocus() {
  isFocused.value = true
  draft.value = String(model.value)
}

function onInput(event: Event) {
  draft.value = onlyDigits((event.target as HTMLInputElement).value)
}

function commit() {
  isFocused.value = false
  const parsed = Number(draft.value)
  if (draft.value !== '' && Number.isFinite(parsed)) {
    model.value = clamp(parsed, props.min, props.max)
  }
}
</script>

<template>
  <div>
    <label :for="id" class="block text-sm text-ink-secondary">{{ label }}</label>
    <div
      class="relative mt-2 rounded-xl bg-surface px-4 pt-3 pb-4 transition focus-within:bg-surface-strong"
    >
      <input
        :id="id"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :readonly="!editable"
        :value="displayValue"
        class="w-full bg-transparent text-lg font-semibold text-ink outline-none lg:text-xl"
        :class="!editable && 'cursor-default'"
        @focus="editable && onFocus()"
        @input="onInput"
        @blur="editable && commit()"
        @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
      />
      <input
        v-model.number="model"
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :aria-label="label"
        :aria-valuetext="formatValue(model)"
        class="range absolute inset-x-3 -bottom-2.5"
        :style="{ '--progress': `${progress}%` }"
      />
    </div>
    <div class="mt-3 flex justify-between text-xs text-ink-secondary">
      <span>{{ formatValue(min) }}</span>
      <span>{{ formatValue(max) }}</span>
    </div>
  </div>
</template>

<style scoped>
.range {
  -webkit-appearance: none;
  appearance: none;
  height: 20px;
  background: transparent;
  cursor: pointer;
}

.range:focus-visible {
  outline: none;
}

.range::-webkit-slider-runnable-track {
  height: 2px;
  border-radius: 1px;
  background: linear-gradient(
    to right,
    var(--color-brand) var(--progress),
    var(--color-line) var(--progress)
  );
}

.range::-webkit-slider-thumb {
  -webkit-appearance: none;
  margin-top: -9px;
  width: 20px;
  height: 20px;
  border: 3px solid #fff;
  border-radius: 9999px;
  background: var(--color-brand);
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.25);
  transition: box-shadow 0.15s;
}

.range:focus-visible::-webkit-slider-thumb {
  box-shadow: 0 0 0 5px rgb(239 49 36 / 0.25);
}

.range::-moz-range-track {
  height: 2px;
  background: var(--color-line);
}

.range::-moz-range-progress {
  height: 2px;
  background: var(--color-brand);
}

.range::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: 3px solid #fff;
  border-radius: 9999px;
  background: var(--color-brand);
  box-shadow: 0 1px 4px rgb(0 0 0 / 0.25);
}

.range:focus-visible::-moz-range-thumb {
  box-shadow: 0 0 0 5px rgb(239 49 36 / 0.25);
}
</style>
