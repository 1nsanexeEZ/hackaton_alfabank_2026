<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { CONSENT_TEXT, PersonalConsentPrompt, personalConsents } from '@/entities/customer'
import type { ConsentDto, ConsentType } from '@/shared/api'
import { errorMessage, formatDate, formatDateTime } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton } from '@/shared/ui'

/**
 * Личные согласия человека: на обработку ПДн (бессрочно) и на запрос своей кредитной истории (6 месяцев).
 * История не перезаписывается: каждое «дать» — новая запись, отзыв только закрывает действующую.
 */
const TYPES: readonly ConsentType[] = ['credit_bureau_personal', 'personal_data']

const { state } = personalConsents
onMounted(() => void personalConsents.load(true))

const revoking = ref<ConsentType | null>(null)
const confirm = ref<ConsentType | null>(null)
const error = ref<string | null>(null)

async function revoke(type: ConsentType) {
  revoking.value = type
  error.value = null
  try {
    await personalConsents.revoke(type)
    confirm.value = null
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    revoking.value = null
  }
}

/** Последняя запись этого типа — чтобы сказать «отозвано» или «истекло», а не просто «нет» */
const latest = (type: ConsentType) => state.items?.find((item) => item.type === type) ?? null

function lapse(item: ConsentDto | null): string {
  if (!item) return 'Не давали'
  if (item.revoked_at) return `Отозвано ${formatDate(item.revoked_at)}`
  return item.valid_until ? `Истекло ${formatDate(item.valid_until)}` : 'Не действует'
}
</script>

<template>
  <section class="space-y-3 border-t border-line pt-5">
    <div>
      <h3 class="text-base font-bold text-ink">Мои согласия</h3>
      <p class="mt-1 text-sm text-ink-secondary">
        Даются за себя, а не за компанию: заявку может заполнять бухгалтер, но свою кредитную историю руководитель
        открывает банку сам.
      </p>
    </div>

    <AsyncState :loading="state.loading && !state.items" :error="state.items ? null : state.error" @retry="personalConsents.load(true)">
      <ul class="space-y-3">
        <li v-for="type in TYPES" :key="type" class="rounded-2xl bg-surface-soft p-4">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <p class="font-semibold text-ink">{{ CONSENT_TEXT[type].title }}</p>
            <BaseBadge v-if="personalConsents.active(type)" tone="success">
              {{ personalConsents.active(type)!.valid_until ? `до ${formatDate(personalConsents.active(type)!.valid_until!)}` : 'бессрочно' }}
            </BaseBadge>
            <BaseBadge v-else>{{ lapse(latest(type)) }}</BaseBadge>
          </div>

          <template v-if="personalConsents.active(type)">
            <p class="mt-1 text-xs text-ink-secondary">Дано {{ formatDateTime(personalConsents.active(type)!.given_at) }}</p>
            <div v-if="confirm === type" class="mt-3 space-y-2">
              <p class="text-sm text-ink">
                Отозвать согласие? Запросы, уже сделанные по заявкам, отзыв не отменяет, а новые банк делать не будет.
              </p>
              <div class="flex flex-wrap gap-2">
                <BaseButton variant="secondary" :loading="revoking === type" @click="revoke(type)">Отозвать</BaseButton>
                <BaseButton variant="ghost" :disabled="revoking === type" @click="confirm = null">Оставить</BaseButton>
              </div>
            </div>
            <button
              v-else
              type="button"
              class="mt-2 text-sm font-medium text-ink-secondary underline underline-offset-2 hover:text-brand"
              @click="confirm = type"
            >
              Отозвать
            </button>
          </template>
          <PersonalConsentPrompt v-else class="mt-3" :type="type" action="Дать согласие" />
        </li>
      </ul>

      <p v-if="error" class="mt-3 text-sm text-brand" role="alert">{{ error }}</p>

      <details v-if="state.items?.length" class="mt-3 text-sm">
        <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">История · {{ state.items.length }}</summary>
        <ul class="mt-2 space-y-1.5 text-xs text-ink-secondary">
          <li v-for="item in state.items" :key="`${item.type}-${item.given_at}`">
            {{ CONSENT_TEXT[item.type]?.title ?? item.type }}: дано {{ formatDateTime(item.given_at) }}
            <template v-if="item.revoked_at"> · отозвано {{ formatDateTime(item.revoked_at) }}</template>
            <template v-else-if="item.valid_until"> · до {{ formatDate(item.valid_until) }}</template>
            · редакция {{ item.text_version }}
          </li>
        </ul>
      </details>
    </AsyncState>
  </section>
</template>
