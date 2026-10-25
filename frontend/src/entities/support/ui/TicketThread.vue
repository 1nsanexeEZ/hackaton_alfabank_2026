<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import type { SupportMessageDto, SupportSide } from '@/shared/api'
import { formatDateTime } from '@/shared/lib'

/**
 * Переписка обращения. Свои сообщения — справа, собеседника — слева; viewer — чьими глазами смотрим.
 * Пришло новое сообщение — лента прокручивается вниз.
 */
const props = defineProps<{ messages: readonly SupportMessageDto[]; viewer: SupportSide }>()

const list = ref<HTMLElement>()
watch(
  () => props.messages.length,
  async () => {
    await nextTick()
    list.value?.scrollTo({ top: list.value.scrollHeight })
  },
  { immediate: true },
)

const SIDE_NAME: Record<SupportSide, string> = { client: 'Клиент', staff: 'Поддержка банка' }
</script>

<template>
  <ol ref="list" class="max-h-[28rem] space-y-3 overflow-y-auto pr-1" aria-label="Переписка">
    <li
      v-for="message in messages"
      :key="message.id"
      class="flex flex-col"
      :class="message.side === viewer ? 'items-end' : 'items-start'"
    >
      <div
        class="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-line"
        :class="message.side === viewer ? 'rounded-br-md bg-ink text-white' : 'rounded-bl-md bg-surface text-ink'"
      >
        {{ message.text }}
      </div>
      <p class="mt-1 px-1 text-xs text-ink-secondary">
        {{ message.side === viewer ? 'Вы' : (message.author_name ?? SIDE_NAME[message.side]) }} · {{ formatDateTime(message.created_at) }}
      </p>
    </li>
  </ol>
</template>
