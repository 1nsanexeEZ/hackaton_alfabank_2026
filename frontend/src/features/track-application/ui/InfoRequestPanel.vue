<script setup lang="ts">
import { CircleCheck, FileUp, MessageSquareWarning } from 'lucide-vue-next'
import { computed } from 'vue'

import { DOCUMENT_TITLE, documentFormat, STATEMENT_TYPE, StatementFormatHint } from '@/entities/application'
import type { CardDocumentDto, InfoRequestDto } from '@/shared/api'
import { formatDateTime } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

/**
 * Дозапрос банка: что просят и зачем, загрузка документов, ответ.
 * Документ сам привязывается к открытому запросу; после ответа заявка возвращается на рассмотрение.
 */
const props = defineProps<{
  request: InfoRequestDto
  /** Загруженные по этому запросу документы — по типам */
  uploaded: Record<string, CardDocumentDto[]>
  uploadErrors: Record<string, string>
  canUpload: boolean
  canAnswer: boolean
  busy: string | null
}>()

const emit = defineEmits<{ upload: [type: string, file: File]; answer: [] }>()

/** Поля из запроса банка — человеческими словами */
const FIELD_LABEL: Record<string, string> = {
  'request.amount': 'сумма кредита',
  'request.term_months': 'срок',
  'request.purpose': 'цель кредита',
  collateral: 'залог',
}

const allUploaded = computed(() => props.request.requested_documents.every((type) => props.uploaded[type]?.length))

const inputs: Record<string, HTMLInputElement | null> = {}

function onChange(type: string, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', type, file)
  input.value = ''
}
</script>

<template>
  <section class="rounded-2xl bg-warning-soft p-5">
    <h3 class="flex items-center gap-2 text-base font-bold text-ink">
      <MessageSquareWarning class="size-5 text-warning" aria-hidden="true" />
      Банку нужны данные
    </h3>
    <p v-if="request.comment" class="mt-2 text-sm text-ink">{{ request.comment }}</p>
    <p v-if="request.due_at" class="mt-1 text-xs text-ink-secondary">Ответить до {{ formatDateTime(request.due_at) }}</p>

    <p v-if="request.requested_fields.length" class="mt-3 text-sm text-ink">
      Уточните: {{ request.requested_fields.map((field) => FIELD_LABEL[field] ?? field).join(', ') }}
    </p>

    <ul v-if="request.requested_documents.length" class="mt-4 space-y-3">
      <li v-for="type in request.requested_documents" :key="type" class="rounded-xl bg-white p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-2 text-sm font-semibold text-ink">
              <CircleCheck v-if="uploaded[type]?.length" class="size-4 shrink-0 text-success" aria-hidden="true" />
              {{ DOCUMENT_TITLE[type] ?? type }}
            </p>
            <p class="mt-0.5 text-xs text-ink-secondary">{{ documentFormat(type).kinds }}, до 20 МБ</p>
            <StatementFormatHint v-if="type === STATEMENT_TYPE" />
          </div>
          <template v-if="canUpload">
            <input
              :ref="(element) => (inputs[type] = element as HTMLInputElement | null)"
              type="file"
              class="sr-only"
              tabindex="-1"
              aria-hidden="true"
              :accept="documentFormat(type).accept"
              @change="onChange(type, $event)"
            />
            <BaseButton
              variant="secondary"
              size="s"
              :loading="busy === `upload:${type}`"
              :disabled="Boolean(busy)"
              @click="inputs[type]?.click()"
            >
              <FileUp v-if="busy !== `upload:${type}`" class="size-4" aria-hidden="true" />
              {{ uploaded[type]?.length ? 'Добавить файл' : 'Загрузить' }}
            </BaseButton>
          </template>
        </div>
        <ul v-if="uploaded[type]?.length" class="mt-2 space-y-1 text-sm text-ink-secondary">
          <li v-for="file in uploaded[type]" :key="file.id" class="truncate">{{ file.filename }}</li>
        </ul>
        <p v-if="uploadErrors[type]" class="mt-2 text-sm text-brand" role="alert">{{ uploadErrors[type] }}</p>
      </li>
    </ul>

    <div v-if="canAnswer" class="mt-5">
      <BaseButton :loading="busy === 'answer'" :disabled="!allUploaded || Boolean(busy)" @click="emit('answer')">
        Отправить ответ банку
      </BaseButton>
      <p v-if="!allUploaded" class="mt-2 text-xs text-ink-secondary">Сначала загрузите все документы, которые просит банк</p>
    </div>
  </section>
</template>
