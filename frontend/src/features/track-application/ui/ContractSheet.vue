<script setup lang="ts">
import { AlertCircle, Check, Copy, Download, ExternalLink, Loader } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { ContractDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { copyText, formatDateTime } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

/**
 * Договор как документ: миниатюра листа, этап (формируется → ждёт подписи → банк подписывает →
 * подписан сторонами), файл, УИд, скачать PDF и проверить подлинность.
 * Пока PDF формируется — ожидание; дольше минуты или сбой — «Обновить».
 */
const props = defineProps<{ contract: ContractDto; busy: string | null; slow: boolean }>()
const emit = defineEmits<{ download: [kind: 'draft' | 'signed']; refresh: [] }>()

const router = useRouter()

/** До подписи нужен проект, после — итоговый с подписью банка */
const kind = computed(() => (props.contract.status === 'unsigned' ? 'draft' : 'signed'))
const document = computed(() => props.contract.document ?? null)
const ready = computed(() => document.value?.status === 'ready' && document.value.kind === kind.value)
const failed = computed(() => document.value?.status === 'failed')
const sealed = computed(() => ready.value && kind.value === 'signed')

const stage = computed(() => {
  if (failed.value) return { label: 'Не удалось сформировать документ', tone: 'text-brand' }
  if (kind.value === 'draft') return ready.value ? { label: 'Проект договора', tone: 'text-ink-secondary' } : { label: 'Договор формируется', tone: 'text-info' }
  return ready.value ? { label: 'Подписан сторонами', tone: 'text-success' } : { label: 'Подписан вами, подписывает банк', tone: 'text-info' }
})

const verifyHref = computed(() => (sealed.value && document.value?.id ? router.resolve(`${ROUTE_PATH.verify}/${document.value.id}`).href : null))

const copied = ref(false)
async function copyUid() {
  if (!props.contract.uid || !(await copyText(props.contract.uid))) return
  copied.value = true
  setTimeout(() => (copied.value = false), 2_000)
}
</script>

<template>
  <article class="flex gap-4 rounded-2xl border border-line p-4 sm:gap-5 sm:p-[1.125rem]">
    <!-- Миниатюра листа: шапка с логотипом, строки текста, таблица условий; проект — водяной знак, подписанный — штамп -->
    <div
      class="sheet relative hidden h-[8.75rem] w-[6.5rem] shrink-0 flex-col gap-[5px] overflow-hidden rounded-lg border border-line bg-white px-2.5 py-3 sm:flex"
      aria-hidden="true"
    >
      <div class="flex items-center gap-1">
        <span class="size-2.5 rounded-[3px] bg-brand" />
        <span class="h-1 w-8 rounded-sm bg-night" />
      </div>
      <span class="mx-auto mt-1.5 mb-1 h-[5px] w-14 rounded-sm bg-night" />
      <span class="sheet__line w-full" />
      <span class="sheet__line w-[86%]" />
      <span class="sheet__line w-full" />
      <span class="mt-1 grid h-8 grid-cols-2 rounded-sm border border-night/15"><span class="border-r border-night/15" /></span>
      <span class="sheet__line w-[72%]" />
      <span v-if="kind === 'draft'" class="absolute top-[54%] left-1/2 -translate-x-1/2 -translate-y-1/2 -rotate-[32deg] text-[1.0625rem] font-black tracking-wider text-brand/25">
        ПРОЕКТ
      </span>
      <span
        v-else-if="sealed"
        class="absolute right-2 bottom-2.5 flex size-[3.375rem] -rotate-[14deg] items-center justify-center rounded-full border-2 border-success/75 text-center text-[0.5rem] leading-tight font-extrabold tracking-wide text-success"
      >
        ПОДПИ-<br />САНО
      </span>
    </div>

    <div class="flex min-w-0 flex-1 flex-col gap-3">
      <div>
        <p class="flex items-center gap-1.5 text-xs font-bold tracking-wider uppercase" :class="stage.tone">
          <Loader v-if="!ready && !failed && !slow" class="size-3.5 animate-spin" aria-hidden="true" />
          <AlertCircle v-else-if="failed || slow" class="size-3.5" aria-hidden="true" />
          {{ slow && !failed && !ready ? 'Документ формируется дольше обычного' : stage.label }}
        </p>
        <h3 class="mt-1 text-base font-extrabold text-ink sm:text-lg">Кредитный договор № {{ contract.number }}</h3>
        <p class="text-sm text-ink-secondary">{{ contract.borrower.name }}</p>
      </div>

      <dl class="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[0.8125rem]">
        <template v-if="ready && document?.filename">
          <dt class="text-ink-secondary">Файл</dt>
          <dd class="break-words text-ink">{{ document.filename }}</dd>
        </template>
        <template v-if="ready && document?.created_at">
          <dt class="text-ink-secondary">{{ kind === 'draft' ? 'Сформирован' : 'Подписан банком' }}</dt>
          <dd class="text-ink">{{ formatDateTime(document.created_at) }}</dd>
        </template>
        <template v-if="contract.uid">
          <dt class="text-ink-secondary">УИд сделки</dt>
          <dd class="flex min-w-0 items-center gap-2">
            <span class="truncate font-mono text-xs text-ink">{{ contract.uid }}</span>
            <button
              type="button"
              class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-surface text-ink transition-colors hover:bg-surface-strong"
              :aria-label="copied ? 'УИд скопирован' : 'Скопировать УИд'"
              @click="copyUid"
            >
              <component :is="copied ? Check : Copy" class="size-3.5" aria-hidden="true" />
            </button>
          </dd>
        </template>
      </dl>

      <div v-if="ready" class="flex flex-wrap items-center gap-2.5">
        <BaseButton size="s" :variant="sealed ? 'primary' : 'secondary'" :loading="busy === `contract:${kind}`" :disabled="Boolean(busy)" @click="emit('download', kind)">
          <Download class="size-4" aria-hidden="true" />
          {{ kind === 'draft' ? 'Скачать проект (PDF)' : 'Скачать подписанный (PDF)' }}
        </BaseButton>
        <a
          v-if="verifyHref"
          :href="verifyHref"
          target="_blank"
          rel="noopener"
          class="inline-flex h-10 items-center gap-2 rounded-lg bg-surface px-4 text-sm font-medium text-ink transition-colors hover:bg-surface-strong"
        >
          Проверить подлинность
          <ExternalLink class="size-4" aria-hidden="true" />
        </a>
      </div>
      <div v-else-if="failed || slow">
        <BaseButton size="s" variant="secondary" @click="emit('refresh')">Обновить</BaseButton>
      </div>
      <p v-else class="text-sm text-ink-secondary" role="status">
        {{ kind === 'draft' ? 'Формируем PDF — несколько секунд' : 'Банк подписывает договор своей электронной подписью — несколько секунд' }}
      </p>
    </div>
  </article>
</template>

<style scoped>
.sheet {
  box-shadow:
    0 1px 2px rgb(18 18 19 / 0.06),
    0 10px 24px rgb(18 18 19 / 0.1);
}

.sheet__line {
  height: 3px;
  border-radius: 2px;
  background: rgb(18 18 19 / 0.14);
}
</style>
