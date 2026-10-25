<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'

import { getAt, pathKey, setAt, type DocPath } from '@/entities/scoring-version'
import type { VersionBody } from '@/shared/api'
import { formatMoney } from '@/shared/lib'

/**
 * Одно поле документа версии по пути. Decimal бэкенда — строки, целые — числа: тип значения
 * сохраняется, как пришёл. percent показывает долю в процентах (0.0050 → 0,5), а пишет долю.
 */
type Kind = 'int' | 'decimal' | 'percent' | 'money' | 'bool'

const props = withDefaults(
  defineProps<{
    body: VersionBody
    path: DocPath
    label: string
    kind: Kind
    errors?: Record<string, string>
    readonly?: boolean
    /** Подпись только для скринридеров — в ячейках таблиц */
    hideLabel?: boolean
    unit?: string
  }>(),
  { errors: () => ({}), readonly: false, hideLabel: false, unit: undefined },
)

const id = useId()
const value = computed(() => getAt(props.body, props.path))
const text = ref('')
const focused = ref(false)
const localError = ref<string | null>(null)
// Ошибка самого поля или его раздела на уровень выше: «grades — границы должны расти» подсвечивает все границы
const error = computed(
  () => localError.value ?? props.errors[pathKey(props.path)] ?? props.errors[pathKey(props.path.slice(0, -1))],
)

const trim = (number: number) => String(Number(number.toFixed(6)))

function show(current: unknown): string {
  if (current === undefined || current === null) return ''
  return props.kind === 'percent' ? trim(Number(current) * 100).replace('.', ',') : String(current).replace('.', ',')
}

// Пока поле в фокусе, не перерисовываем текст из документа: курсор не прыгает
watch(
  value,
  (current) => {
    if (!focused.value) text.value = show(current)
  },
  { immediate: true },
)

function commit(raw: string) {
  text.value = raw
  const normalized = raw.replace(/\s/g, '').replace(',', '.')
  if (!normalized) {
    localError.value = 'Заполните'
    return
  }
  const pattern = props.kind === 'int' ? /^-?\d+$/ : /^-?\d+(\.\d+)?$/
  if (!pattern.test(normalized)) {
    localError.value = props.kind === 'int' ? 'Целое число' : 'Число, например 0,25'
    return
  }
  localError.value = null
  const number = props.kind === 'percent' ? Number(normalized) / 100 : Number(normalized)
  const asString = props.kind === 'percent' ? trim(number) : normalized
  setAt(props.body, props.path, typeof value.value === 'number' || props.kind === 'int' ? number : asString)
}

function onBlur() {
  focused.value = false
  if (!localError.value) text.value = show(value.value)
}

const checked = computed({
  get: () => value.value === true,
  set: (next: boolean) => setAt(props.body, props.path, next),
})

const moneyHint = computed(() =>
  props.kind === 'money' && !localError.value && value.value !== undefined ? formatMoney(Number(value.value)) : null,
)
</script>

<template>
  <label v-if="kind === 'bool'" class="flex items-start gap-2.5 text-sm text-ink" :class="readonly ? 'cursor-default' : 'cursor-pointer'">
    <input v-model="checked" type="checkbox" class="mt-0.5 size-4 shrink-0 accent-brand" :disabled="readonly" />
    <span>{{ label }}<span v-if="error" class="block text-xs text-brand">{{ error }}</span></span>
  </label>

  <div v-else class="min-w-0">
    <label :for="id" :class="hideLabel ? 'sr-only' : 'mb-1 block text-xs font-medium text-ink-secondary'">{{ label }}</label>
    <div class="relative">
      <input
        :id="id"
        :value="text"
        :readonly="readonly"
        inputmode="decimal"
        autocomplete="off"
        :aria-invalid="Boolean(error)"
        :class="[
          'h-9 w-full rounded-lg px-2.5 text-sm text-ink tabular-nums outline-none transition',
          readonly ? 'bg-transparent ring-1 ring-line' : 'bg-surface focus:bg-white focus:ring-2 focus:ring-ink/20',
          unit && 'pr-9',
          error && 'bg-brand-soft ring-1 ring-brand',
        ]"
        @focus="focused = true"
        @blur="onBlur"
        @input="commit(($event.target as HTMLInputElement).value)"
      />
      <span v-if="unit" class="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-ink-muted">{{ unit }}</span>
    </div>
    <p v-if="error" class="mt-1 text-xs text-brand">{{ error }}</p>
    <p v-else-if="moneyHint && !hideLabel" class="mt-1 text-xs text-ink-muted">{{ moneyHint }}</p>
  </div>
</template>
