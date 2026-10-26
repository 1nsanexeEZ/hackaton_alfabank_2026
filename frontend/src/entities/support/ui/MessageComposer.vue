<script setup lang="ts">
import { SendHorizontal } from 'lucide-vue-next'
import { ref, useId } from 'vue'

import { BaseButton } from '@/shared/ui'

/** Поле нового сообщения: Enter или кнопка — отправить, Shift+Enter — новая строка; отправка — забота того, кто встраивает */
withDefaults(defineProps<{ pending?: boolean; placeholder?: string; disabled?: boolean }>(), {
  pending: false,
  placeholder: 'Напишите сообщение',
  disabled: false,
})
const emit = defineEmits<{ send: [text: string, clear: () => void] }>()

/** Как на бэкенде: длиннее — 422 */
const MAX_LENGTH = 4000

const text = ref('')
const hintId = useId()

function send() {
  const value = text.value.trim()
  if (!value) return
  emit('send', value, () => (text.value = ''))
}

function onKeydown(event: KeyboardEvent) {
  // Набор через IME ещё не закончен — Enter подтверждает слово, а не отправляет
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}
</script>

<template>
  <form class="flex items-end gap-2" @submit.prevent="send">
    <label class="min-w-0 flex-1">
      <span class="sr-only">Сообщение</span>
      <textarea
        v-model="text"
        rows="1"
        :maxlength="MAX_LENGTH"
        :placeholder="placeholder"
        :aria-describedby="hintId"
        :disabled="disabled || pending"
        class="block min-h-12 w-full resize-y rounded-xl bg-surface px-4 py-3 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-white focus:ring-2 focus:ring-ink/20 disabled:opacity-60"
        @keydown="onKeydown"
      />
    </label>
    <span :id="hintId" class="sr-only">Enter — отправить, Shift+Enter — новая строка</span>
    <BaseButton type="submit" :loading="pending" :disabled="disabled || !text.trim()" aria-label="Отправить сообщение">
      <SendHorizontal class="size-4" aria-hidden="true" />
    </BaseButton>
  </form>
</template>
