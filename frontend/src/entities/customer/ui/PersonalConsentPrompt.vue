<script setup lang="ts">
import { ref } from 'vue'

import type { ConsentType } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

import { CONSENT_TEXT, personalConsents } from '../model/consents'

/**
 * Дать личное согласие одной кнопкой: текст согласия раскрывается, срок виден сразу.
 * Согласие человек даёт за себя — никаких прав в компании не нужно.
 */
const props = withDefaults(defineProps<{ type?: ConsentType; action?: string }>(), {
  type: 'credit_bureau_personal',
  action: 'Даю согласие',
})

const emit = defineEmits<{ given: [] }>()

const busy = ref(false)
const error = ref<string | null>(null)

async function give() {
  busy.value = true
  error.value = null
  try {
    await personalConsents.give([props.type])
    emit('given')
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="space-y-3">
    <details class="text-xs text-ink-secondary">
      <summary class="cursor-pointer font-medium hover:text-ink">
        Текст согласия «{{ CONSENT_TEXT[type].title }}» · {{ CONSENT_TEXT[type].validity }}
      </summary>
      <p class="mt-2">{{ CONSENT_TEXT[type].body }}</p>
    </details>
    <BaseButton :loading="busy" @click="give">{{ action }}</BaseButton>
    <p v-if="error" class="text-sm text-brand" role="alert">{{ error }}</p>
  </div>
</template>
