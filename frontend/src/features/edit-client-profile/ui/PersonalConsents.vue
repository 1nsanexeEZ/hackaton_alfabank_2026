<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { CONSENT_TEXT, PersonalConsentPrompt, personalConsents } from '@/entities/customer'
import type { ConsentDto, ConsentType } from '@/shared/api'
import { errorMessage, formatDate, formatDateTime } from '@/shared/lib'
import { AsyncState } from '@/shared/ui'

import ConsentCard from './ConsentCard.vue'

/**
 * Личные согласия человека: на обработку ПДн (бессрочно) и на запрос своей кредитной истории (6 месяцев).
 * История не перезаписывается: каждое «дать» — новая запись, отзыв только закрывает действующую.
 */
const TYPES: readonly ConsentType[] = ['credit_bureau_personal', 'personal_data']

const { state } = personalConsents
onMounted(() => void personalConsents.load(true))

const revoking = ref<ConsentType | null>(null)
const error = ref<string | null>(null)

async function revoke(type: ConsentType) {
  revoking.value = type
  error.value = null
  try {
    await personalConsents.revoke(type)
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    revoking.value = null
  }
}

/** Последняя запись этого типа — чтобы сказать «отозвано» или «истекло», а не просто «нет» */
const latest = (type: ConsentType) => state.items?.find((item) => item.type === type) ?? null

function lapse(item: ConsentDto | null): string {
  if (!item) return 'Не дано'
  if (item.revoked_at) return `Отозвано ${formatDate(item.revoked_at)}`
  return item.valid_until ? `Истекло ${formatDate(item.valid_until)}` : 'Не действует'
}

/** Простыми словами: что даёт банку согласие и по какой норме */
const ABOUT: Partial<Record<ConsentType, { description: string; law: string; icon: 'personal' | 'bureau'; confirm: string }>> = {
  credit_bureau_personal: {
    description: 'Банк запрашивает ваш отчёт в бюро кредитных историй — только чтобы рассмотреть заявки компаний, где вы руководитель или учредитель.',
    law: '218-ФЗ, ст. 6',
    icon: 'bureau',
    confirm: 'Запросы, уже сделанные по заявкам, отзыв не отменяет, а новые банк делать не будет.',
  },
  personal_data: {
    description: 'ФИО, должность и контакты — чтобы рассматривать заявки ваших компаний и готовить договоры. Без него заявку не подать.',
    law: '152-ФЗ, ст. 9',
    icon: 'personal',
    confirm: 'Новые заявки без него подать будет нельзя. Поданные рассмотрим до конца.',
  },
}

const cards = computed(() =>
  TYPES.map((type) => {
    const about = ABOUT[type]!
    const active = personalConsents.active(type) ?? null
    return { type, about, active, version: (active ?? latest(type))?.text_version ?? null }
  }),
)

/** Сводка над списком: сколько согласий действует — своих и компаний — и какое истекает первым */
const summary = computed(() => {
  const own = cards.value.map((card) => card.active).filter((item): item is ConsentDto => item !== null)
  const companies = (state.overview ?? [])
    .map((company) => company.consents.find((consent) => consent.type === 'credit_bureau_company'))
    .filter((consent) => consent?.given)
  const ends = [...own.map((item) => item.valid_until), ...companies.map((consent) => consent?.valid_until ?? null)]
    .filter((value): value is string => Boolean(value))
    .sort()
  return { active: own.length + companies.length, nearest: ends[0] ?? null }
})
</script>

<template>
  <section class="space-y-4">
    <div v-if="summary.active" class="flex flex-wrap gap-2">
      <span class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 text-[0.8125rem] font-bold text-success">
        <span class="size-1.5 rounded-full bg-success" aria-hidden="true" />
        {{ summary.active }} {{ summary.active === 1 ? 'действует' : 'действуют' }}
      </span>
      <span v-if="summary.nearest" class="rounded-full bg-surface px-3 py-1 text-[0.8125rem] font-semibold text-ink-secondary">
        Ближайшее истекает {{ formatDate(summary.nearest) }}
      </span>
    </div>

    <h3 class="text-base font-bold text-ink">Мои согласия</h3>

    <AsyncState :loading="state.loading && !state.items" :error="state.items ? null : state.error" @retry="personalConsents.load(true)">
      <div class="space-y-3">
        <ConsentCard
          v-for="card in cards"
          :key="card.type"
          :icon="card.about.icon"
          :title="CONSENT_TEXT[card.type].title"
          :description="card.about.description"
          :law="card.about.law"
          :body="CONSENT_TEXT[card.type].body"
          :active="card.active !== null"
          :inactive-label="lapse(latest(card.type))"
          :given-at="card.active?.given_at ?? null"
          :valid-until="card.active?.valid_until ?? null"
          :text-version="card.version"
          revocable
          :revoking="revoking === card.type"
          :confirm-text="card.about.confirm"
          @revoke="revoke(card.type)"
        >
          <PersonalConsentPrompt :type="card.type" action="Дать согласие" :with-text="false" />
        </ConsentCard>
      </div>

      <p v-if="error" class="mt-3 text-sm text-brand" role="alert">{{ error }}</p>

      <details v-if="state.items?.length" class="mt-4 rounded-2xl bg-surface-soft px-4 py-3 text-sm">
        <summary class="cursor-pointer font-semibold text-ink">История · {{ state.items.length }}</summary>
        <ol class="mt-3 space-y-2.5 border-l-2 border-surface-strong pl-4">
          <li v-for="item in state.items" :key="`${item.type}-${item.given_at}`" class="text-[0.8125rem] leading-relaxed text-ink-secondary">
            <b class="font-semibold text-ink">{{ formatDateTime(item.revoked_at ?? item.given_at) }}</b>
            — {{ item.revoked_at ? 'отозвано' : 'дано' }} согласие «{{ CONSENT_TEXT[item.type]?.title ?? item.type }}»<template
              v-if="!item.revoked_at && item.valid_until"
              >, до {{ formatDate(item.valid_until) }}</template
            >
            · редакция {{ item.text_version }}
          </li>
        </ol>
      </details>
    </AsyncState>
  </section>
</template>
