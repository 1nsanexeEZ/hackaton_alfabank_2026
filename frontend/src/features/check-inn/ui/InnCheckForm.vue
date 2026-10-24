<script setup lang="ts">
import { ChevronDown, Search } from 'lucide-vue-next'
import { reactive, ref } from 'vue'

import { ApiError, backofficeApi, type InnCheckDto, type InnCheckInput, type InnCheckVerdict } from '@/shared/api'
import { errorMessage, onlyDigits } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

import { DEMO_CHECKS } from '../model/demo'

/**
 * Проверка компании по ИНН до заявки (POST /organizations/inn-check). ОГРН, КПП и наименование —
 * по желанию, из документов клиента: бэкенд сверит с ними ИНН. Контрольную цифру ИНН проверяет
 * бэкенд — ошибка в ней тоже ответ проверки, а не ошибка формы.
 */
const emit = defineEmits<{ checked: [result: InnCheckDto] }>()

const form = reactive({ inn: '', ogrn: '', kpp: '', name: '' })
const errors = reactive<{ inn?: string; ogrn?: string; kpp?: string }>({})
const showMatch = ref(false)
const pending = ref(false)
const error = ref<string | null>(null)

const OUTCOME_DOT: Record<InnCheckVerdict, string> = {
  ok: 'bg-success',
  warning: 'bg-warning',
  fail: 'bg-brand',
  not_found: 'bg-ink-muted',
}

function validate(): InnCheckInput | null {
  const inn = onlyDigits(form.inn)
  const ogrn = onlyDigits(form.ogrn)
  const kpp = form.kpp.trim().toUpperCase()
  errors.inn = /^\d{10}$|^\d{12}$/.test(inn) ? undefined : '10 цифр у компании или 12 у ИП'
  errors.ogrn = !ogrn || /^\d{13}$|^\d{15}$/.test(ogrn) ? undefined : '13 цифр у компании или 15 у ИП'
  errors.kpp = !kpp || /^\d{4}[\dA-Z]{2}\d{3}$/.test(kpp) ? undefined : '9 знаков: 770101001'
  if (errors.inn || errors.ogrn || errors.kpp) return null
  // Пустые реквизиты не отправляем — по ним нечего сверять
  return {
    inn,
    ...(ogrn ? { ogrn } : {}),
    ...(kpp ? { kpp } : {}),
    ...(form.name.trim() ? { name: form.name.trim() } : {}),
  }
}

function explain(caught: unknown): string {
  if (caught instanceof ApiError && caught.status === 503) return 'Реестр временно недоступен, повторите позже'
  if (caught instanceof ApiError && caught.status === 403) return 'Проверка по ИНН доступна сотрудникам с правом backoffice.read'
  return errorMessage(caught)
}

async function submit() {
  const input = validate()
  if (!input) return
  pending.value = true
  error.value = null
  try {
    emit('checked', await backofficeApi.innCheck(input))
  } catch (caught) {
    error.value = explain(caught)
  } finally {
    pending.value = false
  }
}

function pick(input: InnCheckInput) {
  Object.assign(form, { inn: input.inn, ogrn: input.ogrn ?? '', kpp: input.kpp ?? '', name: input.name ?? '' })
  showMatch.value = Boolean(input.ogrn || input.kpp || input.name)
  void submit()
}
</script>

<template>
  <div>
    <form novalidate @submit.prevent="submit">
      <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
        <TextField v-model="form.inn" label="ИНН компании или ИП" inputmode="numeric" :maxlength="12" dense :error="errors.inn" placeholder="7701158817" />
        <BaseButton type="submit" :loading="pending" class="sm:mt-7">
          <Search class="size-4" aria-hidden="true" />
          Проверить
        </BaseButton>
      </div>

      <button
        type="button"
        class="mt-3 inline-flex items-center gap-1 text-sm font-medium text-ink-secondary hover:text-ink"
        :aria-expanded="showMatch"
        @click="showMatch = !showMatch"
      >
        Сверить с реквизитами из документов клиента
        <ChevronDown class="size-4 transition-transform" :class="showMatch && 'rotate-180'" aria-hidden="true" />
      </button>
      <div v-if="showMatch" class="mt-3 grid gap-3 sm:grid-cols-3">
        <TextField v-model="form.ogrn" label="ОГРН или ОГРНИП" inputmode="numeric" :maxlength="15" dense :error="errors.ogrn" />
        <TextField v-model="form.kpp" label="КПП" :maxlength="9" dense :error="errors.kpp" />
        <TextField v-model="form.name" label="Наименование" dense placeholder="ООО «Ромашка»" />
      </div>
    </form>
    <p v-if="error" class="mt-3 rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ error }}</p>

    <div class="mt-4">
      <p class="text-xs text-ink-secondary">Демо-компании стенда — точка показывает ожидаемый итог:</p>
      <ul class="mt-2 flex flex-wrap gap-2">
        <li v-for="demo in DEMO_CHECKS" :key="demo.label">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-2 rounded-full bg-surface px-3 text-xs font-medium text-ink transition-colors hover:bg-surface-strong"
            :title="`ИНН ${demo.input.inn}`"
            @click="pick(demo.input)"
          >
            <span class="size-2 shrink-0 rounded-full" :class="OUTCOME_DOT[demo.outcome]" aria-hidden="true" />
            {{ demo.label }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>
