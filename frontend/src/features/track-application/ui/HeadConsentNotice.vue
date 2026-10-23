<script setup lang="ts">
import { UserCheck } from 'lucide-vue-next'
import { ref, watch } from 'vue'

import { PersonalConsentPrompt, personalConsents } from '@/entities/customer'

/**
 * Банк проверяет заявку, а руководитель по реестру не дал согласие на запрос своей кредитной истории
 * (card.consents.head_credit_bureau). Руководителю — кнопка «Дать согласие», остальным — кто должен его дать.
 */
const props = defineProps<{ organizationId: string; headName: string }>()

const emit = defineEmits<{ given: [] }>()

const isHead = ref<boolean | null>(null)

watch(
  () => props.organizationId,
  async (organizationId) => {
    isHead.value = null
    isHead.value = await personalConsents.isRegistryHead(organizationId)
  },
  { immediate: true },
)
</script>

<template>
  <section v-if="isHead !== null" class="rounded-2xl bg-warning-soft p-5">
    <p class="flex items-center gap-2 text-sm font-semibold text-ink">
      <UserCheck class="size-5 shrink-0 text-warning" aria-hidden="true" />
      {{ isHead ? 'Нужно ваше согласие на запрос кредитной истории' : 'Руководитель ещё не дал согласие на запрос кредитной истории' }}
    </p>
    <template v-if="isHead">
      <p class="mt-1 mb-3 text-sm text-ink-secondary">
        Банк смотрит не только компанию, но и личную платёжную дисциплину руководителя. Без вашего согласия эту
        проверку пропустят, и решение будет менее точным.
      </p>
      <PersonalConsentPrompt @given="emit('given')" />
    </template>
    <p v-else class="mt-1 text-sm text-ink-secondary">
      {{ headName }} может дать его в своём кабинете — там уже есть напоминание. Без согласия банк проверит заявку по
      данным компании.
    </p>
  </section>
</template>
