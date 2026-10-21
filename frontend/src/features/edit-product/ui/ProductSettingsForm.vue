<script setup lang="ts">
import { Save } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { creditApi, type ProductSettings } from '@/shared/api'
import { errorMessage, formatDateTime, onlyDigits } from '@/shared/lib'
import { BaseButton, TextField, ToggleSwitch } from '@/shared/ui'

/** Условия кредитного продукта: ставка, суммы, сроки и приём заявок */
const props = defineProps<{ product: ProductSettings; readonly?: boolean }>()
const emit = defineEmits<{ saved: [product: ProductSettings] }>()

const money = (value: number) => value.toLocaleString('ru-RU')

function toForm(product: ProductSettings) {
  return {
    rateFrom: String(product.rateFrom).replace('.', ','),
    amountMin: money(product.amountMin),
    amountMax: money(product.amountMax),
    termMin: String(product.termMin),
    termMax: String(product.termMax),
    decisionTime: product.decisionTime,
    active: product.active,
  }
}

const form = reactive(toForm(props.product))
watch(() => props.product, (product) => Object.assign(form, toForm(product)))

const pending = ref(false)
const error = ref<string | null>(null)
const savedAt = ref<string | null>(null)

const parsed = computed(() => ({
  rateFrom: Number(form.rateFrom.replace(',', '.')),
  amountMin: Number(onlyDigits(form.amountMin)),
  amountMax: Number(onlyDigits(form.amountMax)),
  termMin: Number(onlyDigits(form.termMin)),
  termMax: Number(onlyDigits(form.termMax)),
  decisionTime: form.decisionTime.trim(),
  active: form.active,
}))

const isDirty = computed(() => JSON.stringify(toForm(props.product)) !== JSON.stringify(form))

async function save() {
  const data = parsed.value
  if (!(data.rateFrom > 0 && data.rateFrom < 100)) {
    error.value = 'Ставка должна быть от 0 до 100%'
    return
  }
  pending.value = true
  error.value = null
  try {
    const product = await creditApi.updateProduct(props.product.id, data)
    savedAt.value = product.updatedAt
    emit('saved', product)
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <form class="space-y-4" novalidate @submit.prevent="save">
    <ToggleSwitch
      v-model="form.active"
      label="Принимаем заявки"
      description="Выключенный продукт закрыт для новых заявок"
      :disabled="readonly"
    />
    <fieldset :disabled="readonly" class="grid gap-3 sm:grid-cols-2">
      <TextField v-model="form.rateFrom" label="Ставка от, %" inputmode="decimal" dense />
      <TextField v-model="form.decisionTime" label="Время решения" dense />
      <TextField v-model="form.amountMin" label="Сумма от, ₽" inputmode="numeric" dense />
      <TextField v-model="form.amountMax" label="Сумма до, ₽" inputmode="numeric" dense />
      <TextField v-model="form.termMin" label="Срок от, мес." inputmode="numeric" dense />
      <TextField v-model="form.termMax" label="Срок до, мес." inputmode="numeric" dense />
    </fieldset>
    <p v-if="error" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>
    <div v-if="!readonly" class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-ink-secondary">
        <template v-if="product.updatedAt">Изменено {{ formatDateTime(product.updatedAt) }} · {{ product.updatedBy }}</template>
        <template v-else>Условия из каталога сайта</template>
      </p>
      <BaseButton type="submit" size="s" :disabled="!isDirty" :loading="pending">
        <Save class="size-4" aria-hidden="true" />
        Сохранить
      </BaseButton>
    </div>
  </form>
</template>
