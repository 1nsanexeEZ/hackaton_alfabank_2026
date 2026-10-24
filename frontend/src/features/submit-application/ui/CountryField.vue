<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { COUNTRY_LABEL } from '@/entities/application'
import { SelectField, TextField } from '@/shared/ui'

/** Страна участника для 115-ФЗ: Россия — пустой код, частые страны — списком, любая другая — кодом ISO */
defineProps<{ label?: string; error?: string }>()

const code = defineModel<string>({ required: true })

const OTHER = 'other'
const OPTIONS = [
  { value: '', label: 'Россия' },
  ...Object.entries(COUNTRY_LABEL).map(([value, label]) => ({ value, label })),
  { value: OTHER, label: 'Другая — указать код' },
]

/** «Другая» выбрана, а код ещё не введён — поле для кода всё равно нужно */
const otherChosen = ref(Boolean(code.value) && !(code.value in COUNTRY_LABEL))
// Код подставили снаружи (черновик загрузился): поле для кода — только у страны не из списка
watch(code, (value) => {
  if (value) otherChosen.value = !(value in COUNTRY_LABEL)
})

const choice = computed<string>({
  get: () => (otherChosen.value ? OTHER : code.value),
  set: (value) => {
    otherChosen.value = value === OTHER
    code.value = value === OTHER ? '' : value
  },
})
const custom = computed<string>({
  get: () => code.value,
  set: (value) => (code.value = value.trim().toUpperCase()),
})
</script>

<template>
  <div class="space-y-2">
    <SelectField v-model="choice" :label="label ?? 'Страна'" :options="OPTIONS" dense />
    <TextField
      v-if="otherChosen"
      v-model="custom"
      label="Код страны (ISO, две буквы)"
      placeholder="FR"
      :maxlength="2"
      dense
      :error="error"
    />
  </div>
</template>
