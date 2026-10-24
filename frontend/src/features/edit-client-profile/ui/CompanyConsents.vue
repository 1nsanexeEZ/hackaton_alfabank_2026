<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { CONSENT_TEXT, PersonalConsentPrompt, personalConsents } from '@/entities/customer'
import { errorMessage, formatDate, formatDateTime } from '@/shared/lib'
import { BaseBadge, BaseButton } from '@/shared/ui'

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

const confirm = ref<string | null>(null)
const revoking = ref<string | null>(null)
const error = ref<string | null>(null)

async function revoke(organizationId: string) {
  revoking.value = organizationId
  error.value = null
  try {
    await personalConsents.revokeCompany(organizationId)
    confirm.value = null
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    revoking.value = null
  }
}
</script>

<template>
  <section v-if="companies.length" class="space-y-3 border-t border-line pt-5">
    <div>
      <h3 class="text-base font-bold text-ink">Согласия компаний</h3>
      <p class="mt-1 text-sm text-ink-secondary">
        {{ CONSENT_TEXT.credit_bureau_company.title }} — даётся за компанию до заявки, действует
        {{ CONSENT_TEXT.credit_bureau_company.validity }}. С ним заявку не придётся подтверждать галочкой.
      </p>
    </div>

    <ul class="space-y-3">
      <li v-for="company in companies" :key="company.organizationId" class="rounded-2xl bg-surface-soft p-4">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <p class="font-semibold text-ink">{{ company.organizationName }}</p>
          <BaseBadge v-if="company.consent?.given" tone="success">
            {{ company.consent.valid_until ? `до ${formatDate(company.consent.valid_until)}` : 'действует' }}
          </BaseBadge>
          <BaseBadge v-else>Не дано</BaseBadge>
        </div>

        <template v-if="company.consent?.given">
          <p v-if="company.consent.given_at" class="mt-1 text-xs text-ink-secondary">Дано {{ formatDateTime(company.consent.given_at) }}</p>
          <template v-if="company.canGive">
            <div v-if="confirm === company.organizationId" class="mt-3 space-y-2">
              <p class="text-sm text-ink">
                Отозвать согласие компании? Поданные заявки отзыв не трогает, а для новых согласие понадобится снова.
              </p>
              <div class="flex flex-wrap gap-2">
                <BaseButton variant="secondary" :loading="revoking === company.organizationId" @click="revoke(company.organizationId)">
                  Отозвать
                </BaseButton>
                <BaseButton variant="ghost" :disabled="revoking === company.organizationId" @click="confirm = null">Оставить</BaseButton>
              </div>
            </div>
            <button
              v-else
              type="button"
              class="mt-2 text-sm font-medium text-ink-secondary underline underline-offset-2 hover:text-brand"
              @click="confirm = company.organizationId"
            >
              Отозвать
            </button>
          </template>
        </template>
        <PersonalConsentPrompt
          v-else-if="company.canGive"
          class="mt-3"
          type="credit_bureau_company"
          :organization-id="company.organizationId"
          action="Дать согласие"
        />
        <p v-else class="mt-1 text-xs text-ink-secondary">Даёт представитель компании с правом подавать заявки.</p>
      </li>
    </ul>

    <p v-if="error" class="text-sm text-brand" role="alert">{{ error }}</p>
  </section>
</template>
