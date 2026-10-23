<script setup lang="ts">
import { FlaskConical } from 'lucide-vue-next'

import { API_MODE } from '@/shared/api'

/**
 * Раздел рабочего места, для которого на бэкенде нет ручек: в режиме real он остаётся на моке,
 * и это надо сказать прямо — данные синтетические и живут в браузере.
 */
defineProps<{ text: string }>()
</script>

<template>
  <p v-if="API_MODE === 'real'" class="mb-4 flex items-start gap-2 rounded-xl bg-warning-soft p-3 text-sm text-ink" role="note">
    <FlaskConical class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
    <span><b>Демо.</b> {{ text }}</span>
  </p>
</template>
