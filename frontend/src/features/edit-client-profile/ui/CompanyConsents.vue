<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { CONSENT_TEXT, PersonalConsentPrompt, personalConsents } from '@/entities/customer'
import { errorMessage } from '@/shared/lib'

import ConsentCard from './ConsentCard.vue'

/**
 * Согласия компаний на запрос их кредитной истории (POST/DELETE /organizations/{id}/consents) — до заявки,
 * по схеме банка сразу после выбора условий. Даёт и отзывает любой представитель с правом подавать заявки,
 * за компанию, а не за себя. Черновик заявки берёт действующее согласие сам.
 */
const { state } = personalConsents
onMounted(() => void personalConsents.loadReminders())

const companies = computed(() =>
  (state.overview ?? []).map((item) => ({
    ...item,
    consent: item.consents.find((consent) => consent.type === 'credit_bureau_company') ?? null,
  })),
)

const revoking = ref<string | null>(null)
const error = ref<string | null>(null)

async function revoke(organizationId: string) {
  revoking.value = organizationId
  error.value = null
  try {
    await personalConsents.revokeCompany(organizationId)
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    revoking.value = null
  }
}
</script>

<template>
  <section v-if="companies.length" class="space-y-4">
    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <h3 class="text-base font-bold text-ink">Согласия компаний</h3>
      <span class="text-[0.8125rem] text-ink-secondary">даёт представитель с правом подавать заявки</span>
    </div>

    <div class="space-y-3">
      <ConsentCard
        v-for="company in companies"
        :key="company.organizationId"
        icon="company"
        :caption="company.organizationName"
        :title="CONSENT_TEXT.credit_bureau_company.title"
        description="Пока согласие действует, банк запрашивает отчёт по компании для каждой новой заявки — давать согласие заново не нужно."
        law="218-ФЗ, ст. 6"
        :body="CONSENT_TEXT.credit_bureau_company.body"
        :active="Boolean(company.consent?.given)"
        inactive-label="Не дано"
        :given-at="company.consent?.given_at ?? null"
        :valid-until="company.consent?.valid_until ?? null"
        :revocable="company.canGive"
        :revoking="revoking === company.organizationId"
        confirm-text="Поданные заявки отзыв не трогает, а для новых согласие понадобится снова."
        @revoke="revoke(company.organizationId)"
      >
        <PersonalConsentPrompt
          v-if="company.canGive"
          type="credit_bureau_company"
          :organization-id="company.organizationId"
          action="Дать согласие"
          :with-text="false"
        />
        <p v-else class="text-xs text-ink-secondary">Даёт представитель компании с правом подавать заявки.</p>
      </ConsentCard>
    </div>

    <p v-if="error" class="text-sm text-brand" role="alert">{{ error }}</p>
  </section>
</template>
