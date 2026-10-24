<script setup lang="ts">
import { Plus, Trash2 } from 'lucide-vue-next'

import type { FieldSchema, FieldsSchema } from '@/shared/api'
import { BaseButton, SelectField, TextField } from '@/shared/ui'

import { ENUM_LABEL, newRow, type FieldRow, type FieldValues } from '../model/productFields'

/** Поля заявки, которые продукт описывает JSON Schema: строки, числа, списки значений и списки строк-записей */
defineProps<{
  schema: FieldsSchema
  errors: Record<string, string>
}>()

/** Значения полей — v-model:values: скалярное поле меняем новым объектом, а не правкой пропса */
const values = defineModel<FieldValues>('values', { required: true })

function setScalar(key: string, value: string) {
  values.value = { ...values.value, [key]: value }
}

const isNumeric = (field: FieldSchema) => field.type === 'number' || field.type === 'integer'

const enumOptions = (field: FieldSchema) =>
  (field.enum ?? []).map((value) => ({ value, label: ENUM_LABEL[value] ?? value }))

function rows(key: string): FieldRow[] {
  const value = values.value[key]
  return Array.isArray(value) ? value : []
}

function scalar(key: string): string {
  const value = values.value[key]
  return typeof value === 'string' ? value : ''
}

function addRow(key: string, items: FieldsSchema) {
  rows(key).push(newRow(items))
}

function removeRow(key: string, index: number) {
  rows(key).splice(index, 1)
}

function isRequired(schema: FieldsSchema, key: string) {
  return schema.required?.includes(key) ?? false
}

function label(field: FieldSchema, key: string, required: boolean) {
  return `${field.title ?? key}${required ? '' : ' (необязательно)'}`
}
</script>

<template>
  <div class="space-y-4">
    <template v-for="(field, key) in schema.properties" :key="key">
      <!-- Список записей, например кредиты для рефинансирования -->
      <fieldset v-if="field.type === 'array' && field.items" :data-field="`product_fields.${key}`" class="space-y-3">
        <legend class="mb-2 text-sm font-medium text-ink">{{ field.title ?? key }}</legend>
        <div
          v-for="(row, index) in rows(String(key))"
          :key="index"
          class="rounded-2xl bg-surface-soft p-4"
        >
          <div class="mb-3 flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-ink">№ {{ index + 1 }}</p>
            <button
              v-if="rows(String(key)).length > (field.minItems ?? 1)"
              type="button"
              class="flex size-8 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-white hover:text-brand"
              :aria-label="`Удалить запись ${index + 1}`"
              @click="removeRow(String(key), index)"
            >
              <Trash2 class="size-4" aria-hidden="true" />
            </button>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <template v-for="(inner, name) in field.items.properties" :key="name">
              <SelectField
                v-if="inner.enum"
                :model-value="row[name] ?? ''"
                :label="label(inner, String(name), isRequired(field.items, String(name)))"
                :options="enumOptions(inner)"
                @update:model-value="row[name] = $event"
              />
              <TextField
                v-else
                :model-value="row[name] ?? ''"
                @update:model-value="row[name] = $event"
                :label="label(inner, String(name), isRequired(field.items, String(name)))"
                :inputmode="isNumeric(inner) ? 'decimal' : 'text'"
                :maxlength="inner.maxLength"
                :error="errors[`product_fields.${key}.${index}.${name}`]"
              />
            </template>
          </div>
        </div>
        <p v-if="errors[`product_fields.${key}`]" class="text-sm text-brand">{{ errors[`product_fields.${key}`] }}</p>
        <BaseButton
          v-if="rows(String(key)).length < (field.maxItems ?? 10)"
          variant="secondary"
          size="s"
          @click="addRow(String(key), field.items)"
        >
          <Plus class="size-4" aria-hidden="true" />
          Добавить
        </BaseButton>
      </fieldset>

      <SelectField
        v-else-if="field.enum"
        :data-field="`product_fields.${key}`"
        :model-value="scalar(String(key))"
        :label="label(field, String(key), isRequired(schema, String(key)))"
        :options="enumOptions(field)"
        @update:model-value="setScalar(String(key), $event)"
      />
      <TextField
        v-else
        :data-field="`product_fields.${key}`"
        :model-value="scalar(String(key))"
        @update:model-value="setScalar(String(key), $event)"
        :label="label(field, String(key), isRequired(schema, String(key)))"
        :inputmode="isNumeric(field) ? 'decimal' : 'text'"
        :maxlength="field.maxLength"
        :error="errors[`product_fields.${key}`]"
      />
    </template>
  </div>
</template>
