<script setup lang="ts">
import { ref } from 'vue'

import { errorMessage } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

import { CONSENT_TEXT, personalConsents, type AnyConsentType } from '../model/consents'

/**
 * Дать согласие одной кнопкой: текст согласия раскрывается (или сразу открыт), срок виден сразу.
 * Личное согласие человек даёт за себя — прав в компании не нужно; согласие компании — за компанию
 * organizationId, с правом подавать заявки.
 */
const props = withDefaults(defineProps<{ type?: AnyConsentType; organizationId?: string; action?: string; open?: boolean }>(), {
  type: 'credit_bureau_personal',
  organizationId: undefined,
  action: 'Даю согласие',
  open: false,
})

const emit = defineEmits<{ given: [] }>()

const busy = ref(false)
const error = ref<string | null>(null)

async function give() {
  busy.value = true
  error.value = null
  try {
    await personalConsents.giveAny(props.type, props.organizationId)
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
    <details class="text-xs text-ink-secondary" :open="open">
      <summary class="cursor-pointer font-medium hover:text-ink">
        Текст согласия «{{ CONSENT_TEXT[type].title }}» · {{ CONSENT_TEXT[type].validity }}
      </summary>
      <p class="mt-2">{{ CONSENT_TEXT[type].body }}</p>
    </details>
    <BaseButton :loading="busy" @click="give">{{ action }}</BaseButton>
    <p v-if="error" class="text-sm text-brand" role="alert">{{ error }}</p>
  </div>
</template>
