<script setup lang="ts">
import { AlertCircle, Download, FileText, Loader, ShieldCheck } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import type { ContractDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { formatDateTime } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

/**
 * PDF договора: до подписи — проект, после — итоговый с подписью банка и ссылкой на проверку.
 * Пока документ формируется, показываем ожидание; дольше минуты или сбой — кнопку «Обновить».
 */
const props = defineProps<{ contract: ContractDto; busy: string | null; slow: boolean }>()

const emit = defineEmits<{ download: [kind: 'draft' | 'signed']; refresh: [] }>()

const router = useRouter()

/** Какой документ нужен сейчас: до подписи — проект, после — итоговый */
const kind = computed(() => (props.contract.status === 'unsigned' ? 'draft' : 'signed'))
const document = computed(() => props.contract.document ?? null)
const ready = computed(() => document.value?.status === 'ready' && document.value.kind === kind.value)
const failed = computed(() => document.value?.status === 'failed')

const verifyHref = computed(() =>
  ready.value && kind.value === 'signed' && document.value?.id ? router.resolve(`${ROUTE_PATH.verify}/${document.value.id}`).href : null,
)
</script>

<template>
  <div class="rounded-xl bg-white p-4 text-sm">
    <p class="flex items-center gap-2 font-semibold text-ink">
      <FileText class="size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
      {{ kind === 'draft' ? 'Договор в PDF' : 'Подписанный договор в PDF' }}
    </p>

    <template v-if="ready && document">
      <p v-if="document.filename || document.created_at" class="mt-1 text-xs break-words text-ink-secondary">
        {{ [document.filename, document.created_at && `сформирован ${formatDateTime(document.created_at)}`].filter(Boolean).join(' · ') }}
      </p>
      <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <BaseButton size="s" variant="secondary" :loading="busy === `contract:${kind}`" :disabled="Boolean(busy)" @click="emit('download', kind)">
          <Download class="size-4" aria-hidden="true" />
          {{ kind === 'draft' ? 'Скачать договор (PDF)' : 'Скачать подписанный договор (PDF)' }}
        </BaseButton>
        <a
          v-if="verifyHref"
          :href="verifyHref"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1.5 font-medium text-info underline-offset-2 hover:underline"
        >
          <ShieldCheck class="size-4" aria-hidden="true" />
          Проверить подлинность
        </a>
      </div>
    </template>

    <div v-else-if="failed || slow" class="mt-2 space-y-3">
      <p class="flex items-start gap-2 text-brand" role="alert">
        <AlertCircle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ failed ? 'Не удалось сформировать документ' : 'Документ формируется дольше обычного' }}
      </p>
      <BaseButton size="s" variant="secondary" @click="emit('refresh')">Обновить</BaseButton>
    </div>

    <p v-else class="mt-2 flex items-center gap-2 text-ink-secondary" role="status">
      <Loader class="size-4 shrink-0 animate-spin text-info" aria-hidden="true" />
      {{ kind === 'draft' ? 'Формируем договор — несколько секунд' : 'Банк подписывает договор своей электронной подписью — несколько секунд' }}
    </p>
  </div>
</template>
