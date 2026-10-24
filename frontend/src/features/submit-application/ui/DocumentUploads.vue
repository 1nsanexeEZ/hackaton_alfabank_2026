<script setup lang="ts">
import { CircleCheck, FileUp, Trash2 } from 'lucide-vue-next'

import { documentFormat } from '@/entities/application'
import { BaseButton } from '@/shared/ui'

import type { DocumentSlot } from '../model/useApplicationWizard'

/** Документы, которые требует продукт при этой сумме и форме бизнеса. Файл уходит в хранилище сразу при выборе */
defineProps<{ slots: DocumentSlot[]; errors: Record<string, string>; disabled?: boolean }>()

const emit = defineEmits<{ upload: [type: string, file: File]; remove: [documentId: string] }>()

const inputs: Record<string, HTMLInputElement | null> = {}

function pick(type: string) {
  inputs[type]?.click()
}

function onChange(type: string, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', type, file)
  input.value = ''
}

function size(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`
}
</script>

<template>
  <ul class="space-y-3">
    <li
      v-for="slot in slots"
      :key="slot.type"
      :data-field="`documents.${slot.type}`"
      class="rounded-2xl p-4 transition-colors"
      :class="!slot.files.length && (slot.error || errors[`documents.${slot.type}`]) ? 'bg-brand-soft/60 ring-1 ring-brand/40' : 'bg-surface-soft'"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <p class="flex items-center gap-2 text-sm font-semibold text-ink">
            <CircleCheck v-if="slot.files.length" class="size-4 shrink-0 text-success" aria-hidden="true" />
            {{ slot.title }}
          </p>
          <p class="mt-0.5 text-xs text-ink-secondary">{{ documentFormat(slot.type).kinds }}, до 20 МБ</p>
        </div>
        <input
          :ref="(element) => (inputs[slot.type] = element as HTMLInputElement | null)"
          type="file"
          :accept="documentFormat(slot.type).accept"
          class="sr-only"
          tabindex="-1"
          aria-hidden="true"
          @change="onChange(slot.type, $event)"
        />
        <BaseButton
          variant="secondary"
          size="s"
          :loading="slot.uploading"
          :disabled="disabled || slot.uploading"
          @click="pick(slot.type)"
        >
          <FileUp v-if="!slot.uploading" class="size-4" aria-hidden="true" />
          {{ slot.uploading ? 'Загружаем…' : slot.files.length ? 'Добавить файл' : 'Выбрать файл' }}
        </BaseButton>
      </div>

      <ul v-if="slot.files.length" class="mt-3 space-y-2">
        <li
          v-for="file in slot.files"
          :key="file.id"
          class="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-line"
        >
          <span class="min-w-0 truncate text-ink">{{ file.filename }}</span>
          <span class="flex shrink-0 items-center gap-2">
            <span class="text-xs text-ink-secondary">{{ size(file.size_bytes) }}</span>
            <button
              type="button"
              class="flex size-7 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-surface hover:text-brand"
              :aria-label="`Удалить ${file.filename}`"
              :disabled="disabled"
              @click="emit('remove', file.id)"
            >
              <Trash2 class="size-4" aria-hidden="true" />
            </button>
          </span>
        </li>
      </ul>

      <p v-if="slot.error" class="mt-2 text-sm text-brand" role="alert">{{ slot.error }}</p>
      <p v-else-if="errors[`documents.${slot.type}`]" class="mt-2 text-sm text-brand">
        {{ errors[`documents.${slot.type}`] }}
      </p>
    </li>
  </ul>
</template>
