<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue'

import { clamp, onlyDigits, shakeInvalid } from '../lib'

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
const errorId = `${id}-error`
const input = ref<HTMLInputElement | null>(null)
const isFocused = ref(false)
/** Что набрано — только цифры, без разделителей */
const draft = ref('')
/** Набрали за рамками и ушли из поля — подставили ближнюю границу и коротко говорим об этом */
const corrected = ref('')
let correctedTimer: number | undefined

const progress = computed(() => {
  const span = props.max - props.min
  return span > 0 ? ((model.value - props.min) / span) * 100 : 0
})

/** Пока печатают — цифры группами по три, как в итоге: «3 000 000» */
const groupDigits = (digits: string) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0')

/**
 * Число из того, что набрали или вставили: «3 000 000 ₽» → 3000000, «3000000.00» и «3000000,5» → 3000000.
 * Дробная часть — одна-две цифры после точки или запятой в конце; буквы и знаки отбрасываем.
 */
const wholeDigits = (text: string) => onlyDigits(text.replace(/[.,]\d{0,2}\s*\D*$/, ''))

const displayValue = computed(() => (isFocused.value ? groupDigits(draft.value) : props.formatValue(model.value)))

const typed = computed(() => (draft.value === '' ? null : Number(draft.value)))
/** Ошибка рядом с полем: за рамками — какие рамки; после ухода из поля — что подставили */
const error = computed(() => {
  if (isFocused.value && typed.value !== null) {
    if (typed.value < props.min) return `Минимум — ${props.formatValue(props.min)}`
    if (typed.value > props.max) return `Максимум — ${props.formatValue(props.max)}`
  }
  return isFocused.value ? '' : corrected.value
})

function onFocus() {
  isFocused.value = true
  corrected.value = ''
  draft.value = String(model.value)
}

function onInput(event: Event) {
  const field = event.target as HTMLInputElement
  // Каретку ставим после той же цифры: группировка добавляет и убирает пробелы
  const digitsBefore = onlyDigits(field.value.slice(0, field.selectionStart ?? field.value.length)).length
  draft.value = wholeDigits(field.value).replace(/^0+(?=\d)/, '')
  const shown = groupDigits(draft.value)
  field.value = shown
  let caret = 0
  for (let seen = 0; caret < shown.length && seen < digitsBefore; caret++) if (/\d/.test(shown[caret]!)) seen++
  void nextTick(() => field.setSelectionRange(caret, caret))
}

function commit() {
  isFocused.value = false
  const parsed = typed.value
  if (parsed === null || !Number.isFinite(parsed)) return
  const next = clamp(parsed, props.min, props.max)
  model.value = next
  if (next === parsed) return
  corrected.value = `${next === props.max ? 'Максимум' : 'Минимум'} — ${props.formatValue(next)}, поставили его`
  shakeInvalid([input.value?.parentElement])
  window.clearTimeout(correctedTimer)
  correctedTimer = window.setTimeout(() => (corrected.value = ''), 4000)
}
</script>

<template>
  <div>
    <label :for="id" class="block text-sm text-ink-secondary">{{ label }}</label>
    <div
      class="relative mt-2 rounded-xl bg-surface px-4 pt-3 pb-4 transition focus-within:bg-surface-strong"
      :class="error && 'ring-2 ring-brand'"
    >
      <input
        :id="id"
        ref="input"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :readonly="!editable"
        :value="displayValue"
        class="w-full bg-transparent text-lg font-semibold text-ink outline-none lg:text-xl"
        :class="!editable && 'cursor-default'"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="error ? errorId : undefined"
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
    <p v-if="error" :id="errorId" class="mt-3 text-xs text-brand" role="status">{{ error }}</p>
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
