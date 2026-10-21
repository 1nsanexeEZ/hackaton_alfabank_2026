<script setup lang="ts">
import { AlertCircle, Inbox } from 'lucide-vue-next'

import BaseButton from './BaseButton.vue'

/** Загрузка, ошибка и пустой результат в одном месте, чтобы страницы не повторяли эти состояния */
withDefaults(
  defineProps<{
    loading: boolean
    error?: string | null
    empty?: boolean
    emptyText?: string
  }>(),
  { error: null, empty: false, emptyText: 'Здесь пока пусто' },
)

defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="loading" class="flex items-center justify-center gap-3 py-16 text-sm text-ink-secondary" role="status">
    <span class="size-5 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
    Загружаем…
  </div>
  <div v-else-if="error" class="flex flex-col items-center gap-3 px-4 py-14 text-center" role="alert">
    <AlertCircle class="size-8 text-brand" aria-hidden="true" />
    <p class="max-w-sm text-sm text-ink">{{ error }}</p>
    <BaseButton variant="secondary" size="s" @click="$emit('retry')">Повторить</BaseButton>
  </div>
  <div v-else-if="empty" class="flex flex-col items-center gap-3 px-4 py-14 text-center text-sm text-ink-secondary">
    <Inbox class="size-8 text-ink-muted" aria-hidden="true" />
    {{ emptyText }}
  </div>
  <slot v-else />
</template>
