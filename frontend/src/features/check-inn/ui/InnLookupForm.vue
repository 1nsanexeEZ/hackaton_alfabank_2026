<script setup lang="ts">
import { Search } from 'lucide-vue-next'
import { reactive, ref } from 'vue'

import { creditApi, DOSSIERS, dossierInn, dossierName, type Dossier, type ScoreResult } from '@/shared/api'
import { errorMessage, isValidInn, onlyDigits } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/** Проверка контрагента: досье из внешних источников и предварительный скоринг на сумму */
const emit = defineEmits<{ result: [value: { dossier: Dossier; score: ScoreResult } | null, inn: string] }>()

const form = reactive({ inn: '', amount: '3 000 000' })
const errors = reactive<{ inn?: string; amount?: string }>({})
const pending = ref(false)
const error = ref<string | null>(null)

// Внешние источники пока моки — подсказываем синтетические ИНН, которые есть в данных
const SAMPLES = DOSSIERS.map((item) => ({ inn: dossierInn(item), name: dossierName(item) }))

async function submit() {
  const inn = onlyDigits(form.inn)
  const amount = Number(onlyDigits(form.amount))
  errors.inn = isValidInn(inn) ? undefined : 'Проверьте ИНН: 10 цифр для компании или 12 для ИП'
  errors.amount = amount > 0 ? undefined : 'Укажите сумму кредита'
  if (errors.inn || errors.amount) return

  pending.value = true
  error.value = null
  try {
    emit('result', await creditApi.lookupInn(inn, amount), inn)
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}

function pick(inn: string) {
  form.inn = inn
  void submit()
}
</script>

<template>
  <div>
    <form class="grid gap-3 sm:grid-cols-[1fr_14rem_auto] sm:items-start" novalidate @submit.prevent="submit">
      <TextField v-model="form.inn" label="ИНН компании или ИП" inputmode="numeric" :maxlength="12" dense :error="errors.inn" placeholder="7720123457" />
      <TextField v-model="form.amount" label="Сумма кредита, ₽" inputmode="numeric" dense :error="errors.amount" />
      <BaseButton type="submit" :loading="pending" class="sm:mt-7">
        <Search class="size-4" aria-hidden="true" />
        Проверить
      </BaseButton>
    </form>
    <p v-if="error" class="mt-3 rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>

    <div v-if="SAMPLES.length" class="mt-4">
      <p class="text-xs text-ink-secondary">Синтетические компании для проверки:</p>
      <ul class="mt-2 flex flex-wrap gap-2">
        <li v-for="sample in SAMPLES" :key="sample.inn">
          <button
            type="button"
            class="h-8 rounded-full bg-surface px-3 text-xs font-medium text-ink transition-colors hover:bg-surface-strong"
            @click="pick(sample.inn)"
          >
            {{ sample.name }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>
