<script setup lang="ts">
import { AlertCircle, CircleCheck, Loader, PenLine } from 'lucide-vue-next'
import { computed } from 'vue'

import type { ContractDto } from '@/shared/api'

/**
 * Где договор: формируется → ждёт подписи клиента → клиент подписал, подписывает банк → подписан сторонами.
 * Этап считаем по статусу договора и его PDF; сбой формирования отмечаем на текущем этапе.
 */
const props = defineProps<{ contract: ContractDto }>()

const STAGES = ['Договор формируется', 'Ожидает вашей подписи', 'Подписан вами, подписывает банк', 'Подписан сторонами'] as const

const current = computed(() => {
  const document = props.contract.document
  if (props.contract.status === 'unsigned') return document?.kind === 'draft' && document.status === 'ready' ? 1 : 0
  return document?.kind === 'signed' && document.status === 'ready' ? 3 : 2
})
const failed = computed(() => props.contract.document?.status === 'failed')

type State = 'done' | 'waiting' | 'yours' | 'failed' | 'next'

function stateOf(index: number): State {
  if (index < current.value || (index === 3 && current.value === 3)) return 'done'
  if (index > current.value) return 'next'
  if (failed.value) return 'failed'
  return index === 1 ? 'yours' : 'waiting'
}
</script>

<template>
  <ol class="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4" aria-label="Этапы подписания договора">
    <li
      v-for="(title, index) in STAGES"
      :key="title"
      class="flex items-start gap-2 rounded-xl px-2.5 py-2 text-xs"
      :class="stateOf(index) === 'next' ? 'text-ink-muted' : 'bg-white text-ink'"
      :aria-current="index === current ? 'step' : undefined"
    >
      <CircleCheck v-if="stateOf(index) === 'done'" class="size-4 shrink-0 text-success" aria-hidden="true" />
      <AlertCircle v-else-if="stateOf(index) === 'failed'" class="size-4 shrink-0 text-brand" aria-hidden="true" />
      <PenLine v-else-if="stateOf(index) === 'yours'" class="size-4 shrink-0 text-brand" aria-hidden="true" />
      <Loader v-else-if="stateOf(index) === 'waiting'" class="size-4 shrink-0 animate-spin text-info" aria-hidden="true" />
      <span v-else class="mt-0.5 size-3 shrink-0 rounded-full border-2 border-ink-muted" aria-hidden="true" />
      <span :class="index === current && 'font-semibold'">{{ title }}</span>
    </li>
  </ol>
</template>
