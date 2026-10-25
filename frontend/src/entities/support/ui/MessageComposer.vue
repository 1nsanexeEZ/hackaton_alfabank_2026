<script setup lang="ts">
import { SendHorizontal } from 'lucide-vue-next'
import { ref } from 'vue'

import { BaseButton } from '@/shared/ui'

/** Поле нового сообщения: Ctrl+Enter или кнопка — отправить; отправка — забота того, кто встраивает */
withDefaults(defineProps<{ pending?: boolean; placeholder?: string; disabled?: boolean }>(), {
  pending: false,
  placeholder: 'Напишите сообщение',
  disabled: false,
})
const emit = defineEmits<{ send: [text: string, clear: () => void] }>()

/** Как на бэкенде: длиннее — 422 */
const MAX_LENGTH = 4000

const text = ref('')

function send() {
  const value = text.value.trim()
  if (!value) return
  emit('send', value, () => (text.value = ''))
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) send()
}
</script>

<template>
  <form class="flex items-end gap-2" @submit.prevent="send">
    <label class="min-w-0 flex-1">
      <span class="sr-only">Сообщение</span>
      <textarea
        v-model="text"
        rows="2"
        :maxlength="MAX_LENGTH"
        :placeholder="placeholder"
        :disabled="disabled || pending"
        class="block w-full resize-y rounded-xl bg-surface px-4 py-3 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-white focus:ring-2 focus:ring-ink/20 disabled:opacity-60"
        @keydown="onKeydown"
      />
    </label>
    <BaseButton type="submit" :loading="pending" :disabled="disabled || !text.trim()" aria-label="Отправить сообщение">
      <SendHorizontal class="size-4" aria-hidden="true" />
    </BaseButton>
  </form>
</template>
