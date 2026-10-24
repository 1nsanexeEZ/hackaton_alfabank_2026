<script setup lang="ts">
import { AlertCircle, CircleCheck, FileUp, Loader } from 'lucide-vue-next'
import { computed, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'

import { clientApi, type FileVerificationDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { errorMessage, formatMoscowDateTime } from '@/shared/lib'

/**
 * Проверка файла: клиент или контрагент загружает PDF, банк сверяет его с архивом и проверяет свою подпись
 * (POST /contracts/verify). Файл никуда не сохраняется — только сверка.
 */
const props = defineProps<{ documentId: string }>()

const MAX_BYTES = 10 * 1024 * 1024

const PROBLEM: Record<string, string> = {
  not_in_archive: 'Такого файла нет в архиве банка: это другой документ или его изменили',
  no_signature: 'В файле нет электронной подписи банка',
  signature_broken: 'Файл изменён после подписания',
  untrusted_certificate: 'Подпись сделана сертификатом, которому банк не доверяет',
  draft_not_signed: 'Это проект договора: стороны его ещё не подписали',
}

const router = useRouter()

const dragging = ref(false)
const checking = ref(false)
const fileName = ref<string | null>(null)
const result = shallowRef<FileVerificationDto | null>(null)
const error = ref<string | null>(null)

/** Список проблем по-человечески; если бэкенд кодов не дал — выводим из флагов подписи */
const problems = computed(() => {
  const value = result.value
  if (!value || value.valid) return []
  const codes = value.problems.length
    ? value.problems
    : [
        !value.matches_archive && 'not_in_archive',
        !value.signature.present && 'no_signature',
        value.signature.present && !value.signature.intact && 'signature_broken',
        value.signature.present && !value.signature.trusted && 'untrusted_certificate',
      ].filter((code): code is string => Boolean(code))
  return codes.length ? codes.map((code) => PROBLEM[code] ?? code) : ['Документ не прошёл проверку']
})

/** Файл — другой документ из архива: даём открыть его проверку */
const otherDocumentHref = computed(() => {
  const id = result.value?.document_id
  return id && id !== props.documentId ? router.resolve(`${ROUTE_PATH.verify}/${id}`).href : null
})

async function check(file: File | undefined) {
  if (!file) return
  fileName.value = file.name
  result.value = null
  error.value = null
  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    error.value = 'Это не PDF-файл — выберите договор в формате PDF'
    return
  }
  if (file.size > MAX_BYTES) {
    error.value = 'Файл больше 10 МБ'
    return
  }
  checking.value = true
  try {
    result.value = await clientApi.verifyContractFile(file)
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    checking.value = false
  }
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement
  void check(input.files?.[0])
  // Тот же файл можно выбрать ещё раз
  input.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  void check(event.dataTransfer?.files[0])
}
</script>

<template>
  <section class="rounded-2xl bg-white p-5 shadow-sm sm:p-6">
    <h2 class="text-base font-bold text-ink">Проверить файл</h2>
    <p class="mt-1 text-sm text-ink-secondary">
      Загрузите PDF договора, который у вас на руках: банк сверит его с архивом и проверит свою подпись.
    </p>

    <label
      class="mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 text-center text-sm transition-colors"
      :class="dragging ? 'border-info bg-info-soft' : 'border-line hover:border-ink-muted'"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <Loader v-if="checking" class="size-6 animate-spin text-info" aria-hidden="true" />
      <FileUp v-else class="size-6 text-ink-secondary" aria-hidden="true" />
      <span class="font-medium text-ink">{{ checking ? 'Проверяем…' : 'Выберите PDF или перетащите его сюда' }}</span>
      <span v-if="fileName" class="max-w-full truncate text-xs text-ink-secondary">{{ fileName }}</span>
      <span v-else class="text-xs text-ink-secondary">до 10 МБ</span>
      <input type="file" accept="application/pdf,.pdf" class="sr-only" :disabled="checking" @change="onPick" />
    </label>

    <p v-if="error" class="mt-4 flex items-start gap-2 rounded-xl bg-brand-soft p-4 text-sm text-brand" role="alert">
      <AlertCircle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {{ error }}
    </p>

    <div v-else-if="result?.valid" class="mt-4 rounded-xl bg-success-soft p-4 text-sm" role="status">
      <p class="flex items-center gap-2 font-semibold text-success">
        <CircleCheck class="size-5 shrink-0" aria-hidden="true" />
        Документ подлинный и не изменялся
      </p>
      <p v-if="result.signature.signer" class="mt-2 text-ink">
        Подпись: {{ result.signature.signer
        }}<template v-if="result.signature.signed_at">, {{ formatMoscowDateTime(result.signature.signed_at) }}</template>
      </p>
      <p v-if="otherDocumentHref" class="mt-2 text-ink">
        Это другой документ из архива банка —
        <a :href="otherDocumentHref" class="font-medium text-info underline underline-offset-2">открыть его проверку</a>
      </p>
    </div>

    <div v-else-if="result" class="mt-4 rounded-xl bg-brand-soft p-4 text-sm" role="alert">
      <p class="flex items-center gap-2 font-semibold text-brand">
        <AlertCircle class="size-5 shrink-0" aria-hidden="true" />
        Документ не прошёл проверку
      </p>
      <ul class="mt-2 space-y-1 text-ink">
        <li v-for="problem in problems" :key="problem">• {{ problem }}</li>
      </ul>
    </div>
  </section>
</template>
