<script setup lang="ts">
import { AlertCircle, CircleCheck, FileQuestion, FileText, Info, RefreshCw } from 'lucide-vue-next'
import { computed, ref, shallowRef, watch } from 'vue'

import { ApiError, clientApi, type ContractVerificationDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { errorMessage, formatMoscowDateTime } from '@/shared/lib'
import { AppLogo, BaseButton } from '@/shared/ui'

import FileCheck from './FileCheck.vue'
import SignatureStamp from './SignatureStamp.vue'

/**
 * Публичная проверка договора по QR-коду из PDF (GET /contracts/verify/{id}), без входа.
 * Кто и когда подписал, сертификат банка и сверка загруженного файла с архивом.
 * Открывают с телефона — вёрстка в одну колонку, не шире 720 px.
 */
const props = defineProps<{ id: string }>()

const contract = shallowRef<ContractVerificationDto | null>(null)
const state = ref<'loading' | 'ready' | 'not_found' | 'error'>('loading')
const errorText = ref<string | null>(null)
const showHash = ref(false)

async function load() {
  state.value = 'loading'
  showHash.value = false
  try {
    contract.value = await clientApi.verifyContract(props.id)
    state.value = 'ready'
  } catch (caught) {
    contract.value = null
    if (caught instanceof ApiError && caught.status === 404) {
      state.value = 'not_found'
    } else {
      errorText.value = errorMessage(caught)
      state.value = 'error'
    }
  }
}

watch(() => props.id, load, { immediate: true })

const signedByBank = computed(() => contract.value?.signatures.some((signature) => signature.party === 'bank') ?? false)

const rows = computed(() => {
  const value = contract.value
  if (!value) return []
  return [
    { label: 'Номер договора', value: value.number },
    { label: 'УИд договора', value: value.uid, mono: true },
    { label: 'Заёмщик', value: value.borrower },
    { label: 'Документ', value: value.kind === 'signed' ? 'Подписанный договор' : 'Проект договора, до подписания' },
    { label: 'Сформирован', value: formatMoscowDateTime(value.created_at) },
  ]
})
</script>

<template>
  <div class="min-h-dvh bg-surface">
    <header class="border-b border-line bg-white">
      <div class="mx-auto flex max-w-[720px] items-center px-4 py-3 sm:px-6">
        <RouterLink :to="ROUTE_PATH.home" aria-label="На главную">
          <AppLogo />
        </RouterLink>
      </div>
    </header>

    <main class="mx-auto max-w-[720px] space-y-5 px-4 py-6 sm:px-6 sm:py-10">
      <h1 class="text-xl font-bold text-ink sm:text-2xl">Проверка электронного договора</h1>

      <section v-if="state === 'loading'" class="rounded-2xl bg-white p-6 shadow-sm" aria-busy="true">
        <div class="h-5 w-2/3 animate-pulse rounded bg-surface" />
        <div class="mt-4 space-y-2">
          <div v-for="line in 4" :key="line" class="h-4 animate-pulse rounded bg-surface" />
        </div>
        <p class="sr-only">Загружаем сведения о договоре</p>
      </section>

      <section v-else-if="state === 'not_found'" class="rounded-2xl bg-white p-6 text-center shadow-sm">
        <FileQuestion class="mx-auto size-10 text-ink-muted" aria-hidden="true" />
        <p class="mt-3 text-base font-bold text-ink">Документ не найден в архиве банка</p>
        <p class="mt-1 text-sm text-ink-secondary">
          Проверьте ссылку или отсканируйте QR-код ещё раз. Если документ у вас на руках, загрузите его ниже — банк сверит
          файл с архивом.
        </p>
      </section>

      <section v-else-if="state === 'error'" class="rounded-2xl bg-white p-6 shadow-sm">
        <p class="flex items-start gap-2 text-sm text-brand" role="alert">
          <AlertCircle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Не удалось получить сведения о договоре. {{ errorText }}
        </p>
        <BaseButton class="mt-4" size="s" variant="secondary" @click="load">
          <RefreshCw class="size-4" aria-hidden="true" />
          Повторить
        </BaseButton>
      </section>

      <template v-else-if="contract">
        <section class="rounded-2xl bg-white p-5 shadow-sm sm:p-6">
          <p
            class="flex items-start gap-2 rounded-xl p-3 text-sm font-semibold"
            :class="contract.kind === 'signed' && signedByBank ? 'bg-success-soft text-success' : 'bg-info-soft text-info'"
          >
            <CircleCheck v-if="contract.kind === 'signed' && signedByBank" class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <FileText v-else class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{
              contract.kind === 'signed' && signedByBank
                ? 'Договор есть в архиве банка и подписан сторонами'
                : 'Это проект договора: стороны его ещё не подписали'
            }}
          </p>

          <dl class="mt-4 divide-y divide-line text-sm">
            <div v-for="row in rows" :key="row.label" class="grid gap-1 py-2.5 sm:grid-cols-[10rem_1fr] sm:gap-3">
              <dt class="text-ink-secondary">{{ row.label }}</dt>
              <dd class="text-ink" :class="row.mono ? 'font-mono text-xs break-all sm:text-sm' : 'font-medium break-words'">{{ row.value }}</dd>
            </div>
            <div class="grid gap-1 py-2.5 sm:grid-cols-[10rem_1fr] sm:gap-3">
              <dt class="text-ink-secondary">SHA-256 файла</dt>
              <dd>
                <span v-if="showHash" class="font-mono text-xs break-all text-ink">{{ contract.sha256 }}</span>
                <button
                  v-else
                  type="button"
                  class="font-medium text-info underline underline-offset-2"
                  @click="showHash = true"
                >
                  Показать
                </button>
              </dd>
            </div>
          </dl>
        </section>

        <p
          class="flex items-start gap-2 rounded-2xl p-4 text-sm text-ink"
          :class="contract.log_intact ? 'bg-success-soft' : 'bg-brand-soft'"
          :role="contract.log_intact ? 'note' : 'alert'"
        >
          <CircleCheck v-if="contract.log_intact" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          <AlertCircle v-else class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
          <template v-if="contract.log_intact">Журнал подписания цел: записи о подписях не менялись и не удалялись.</template>
          <template v-else>Журнал подписания нарушен: цепочка записей о подписях не сходится. Обратитесь в банк.</template>
        </p>

        <p v-if="contract.demo" class="flex items-start gap-2 rounded-2xl bg-warning-soft p-4 text-sm text-ink" role="note">
          <Info class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
          Демо-стенд: ключ банка не квалифицированный. Подпись банка показывает, что файл не менялся после подписания,
          но не заменяет квалифицированную электронную подпись.
        </p>

        <section v-if="contract.signatures.length" class="space-y-3">
          <h2 class="text-base font-bold text-ink">Подписи</h2>
          <SignatureStamp
            v-for="signature in contract.signatures"
            :key="`${signature.party}-${signature.signed_at}`"
            class="bg-white"
            :signature="signature"
          />
        </section>
      </template>

      <FileCheck v-if="state !== 'loading'" :document-id="id" />
    </main>
  </div>
</template>
