<script setup lang="ts">
import { CircleCheck, CircleX, ShieldQuestion } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { errorMessage, formatDate } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

import { personalConsents } from '../model/consents'
import { founderPrescreen } from '../model/prescreen'
import PersonalConsentPrompt from './PersonalConsentPrompt.vue'

/**
 * Предскрининг учредителя стартапа: банк смотрит личную кредитную историю учредителя (руководителя по
 * реестру) — только с его согласия. Пройден и не истёк (30 дней) — можно подавать заявку на продукт для
 * стартапа; без него такая заявка получит отказ. Проверку запускает любой участник с правом подачи.
 */
const props = defineProps<{ organizationId: string }>()

const info = computed(() => founderPrescreen.state[props.organizationId] ?? null)
const prescreen = computed(() => info.value?.prescreen ?? null)

const isFounder = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)

watch(
  () => props.organizationId,
  async (organizationId) => {
    error.value = null
    const [, founder] = await Promise.all([
      founderPrescreen.load(organizationId),
      personalConsents.isRegistryHead(organizationId),
      personalConsents.load(),
    ])
    if (organizationId === props.organizationId) isFounder.value = founder
  },
  { immediate: true },
)

/** Учредителю без действующего согласия сначала нужно его дать — иначе бэкенд ответит consent_required */
const needsConsent = computed(() => isFounder.value && !personalConsents.active('credit_bureau_personal'))

const failed = computed(() => prescreen.value?.reasons.filter((reason) => !reason.passed) ?? [])

async function run() {
  busy.value = true
  error.value = null
  try {
    await founderPrescreen.run(props.organizationId)
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="rounded-2xl bg-surface-soft p-5">
    <p class="flex items-center gap-2 font-semibold text-ink">
      <ShieldQuestion class="size-5 shrink-0 text-brand" aria-hidden="true" />
      Проверка учредителя
    </p>
    <p class="mt-1 text-sm text-ink-secondary">
      У нового бизнеса ещё нет оборотов и отчётности, поэтому банк сначала смотрит личную кредитную историю
      учредителя. Проверка действует 30 дней.
    </p>

    <div v-if="prescreen" class="mt-4 rounded-xl bg-white p-4 text-sm">
      <p v-if="prescreen.status === 'passed' && prescreen.valid" class="flex items-center gap-2 font-medium text-success">
        <CircleCheck class="size-4" aria-hidden="true" />
        Пройдена · {{ prescreen.founderName }} · действует до {{ formatDate(prescreen.validUntil) }}
      </p>
      <p v-else-if="prescreen.status === 'passed'" class="font-medium text-warning">
        Срок проверки истёк {{ formatDate(prescreen.validUntil) }} — пройдите её заново
      </p>
      <template v-else>
        <p class="flex items-center gap-2 font-medium text-brand">
          <CircleX class="size-4" aria-hidden="true" />
          Не пройдена · {{ prescreen.founderName }} · {{ formatDate(prescreen.checkedAt) }}
        </p>
        <ul class="mt-2 space-y-0.5 text-ink-secondary">
          <li v-for="reason in failed" :key="reason.code">• {{ reason.message }}</li>
        </ul>
        <p class="mt-2 text-ink-secondary">Кредит на запуск бизнеса сейчас не получить. Проверку можно пройти снова позже.</p>
      </template>
    </div>
    <p v-else-if="info" class="mt-4 text-sm text-ink">Проверку ещё не проходили.</p>

    <div v-if="!(prescreen?.status === 'passed' && prescreen.valid)" class="mt-4">
      <template v-if="needsConsent">
        <p class="mb-3 text-sm text-ink">Для проверки нужно ваше согласие на запрос кредитной истории.</p>
        <PersonalConsentPrompt action="Дать согласие" />
      </template>
      <BaseButton v-else :loading="busy" @click="run">{{ prescreen ? 'Пройти проверку снова' : 'Пройти проверку' }}</BaseButton>
      <p v-if="!isFounder && !needsConsent" class="mt-2 text-xs text-ink-secondary">
        Проверяется учредитель по реестру — для проверки нужно его согласие на запрос кредитной истории в его кабинете.
      </p>
      <p v-if="error" class="mt-2 text-sm text-brand" role="alert">{{ error }}</p>
    </div>
  </section>
</template>
