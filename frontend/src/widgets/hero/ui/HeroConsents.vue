<script setup lang="ts">
import { CircleCheck, CircleDashed } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { CONSENT_TEXT, PersonalConsentPrompt, personalConsents, useCustomer, type AnyConsentType } from '@/entities/customer'
import type { ConsentStateDto } from '@/shared/api'
import { formatDate } from '@/shared/lib'
import { BaseModal } from '@/shared/ui'

/**
 * Согласия для заявок на первом экране (Dashboard.consents): по схеме банка они даются до заявки, сразу
 * после выбора условий, и черновик берёт их сам. Личные — один раз за себя, на БКИ компании — за каждую
 * компанию. «Дать» открывает текст согласия: без него соглашаться не на что.
 */
const { me } = useCustomer()

watch(
  () => me.value?.id,
  (id) => id && void personalConsents.loadReminders(),
  { immediate: true },
)

const SHORT_TITLE: Record<AnyConsentType, string> = {
  personal_data: 'Обработка персональных данных',
  credit_bureau_company: 'Кредитная история компании',
  credit_bureau_personal: 'Ваша кредитная история',
}

interface Row {
  key: string
  consent: ConsentStateDto
  organizationId: string
  /** У согласия компании — чья компания, если компаний несколько */
  companyName: string | null
  canGive: boolean
}

/** Личные согласия — по одному разу, согласие компании — по каждой компании */
const rows = computed<Row[]>(() => {
  const overview = personalConsents.state.overview ?? []
  const several = overview.length > 1
  const personal = new Map<string, Row>()
  const company: Row[] = []
  for (const item of overview) {
    for (const consent of item.consents) {
      if (consent.scope === 'organization') {
        company.push({
          key: `${consent.type}:${item.organizationId}`,
          consent,
          organizationId: item.organizationId,
          companyName: several ? item.organizationName : null,
          canGive: item.canGive,
        })
      } else if (!personal.has(consent.type)) {
        personal.set(consent.type, { key: consent.type, consent, organizationId: item.organizationId, companyName: null, canGive: true })
      }
    }
  }
  const all = [...personal.values(), ...company]
  return all.sort((a, b) => order(a.consent.type) - order(b.consent.type))
})
const order = (type: AnyConsentType) => ['personal_data', 'credit_bureau_company', 'credit_bureau_personal'].indexOf(type)

const missingRequired = computed(() => rows.value.filter((row) => row.consent.required && !row.consent.given).length)

const giving = ref<Row | null>(null)
const modalOpen = computed({
  get: () => giving.value !== null,
  set: (open) => {
    if (!open) giving.value = null
  },
})
</script>

<template>
  <section v-if="rows.length" class="rounded-3xl bg-night-glass p-5" aria-label="Согласия для заявок">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <p class="text-sm font-semibold">Согласия для заявок</p>
      <p class="text-xs text-on-night-secondary">
        {{ missingRequired ? 'Без обязательных заявку не подать' : 'Обязательные даны — галочки в заявке уже стоят' }}
      </p>
    </div>
    <ul class="mt-3 space-y-2">
      <li v-for="row in rows" :key="row.key" class="flex items-center justify-between gap-3 text-sm" :title="row.consent.purpose">
        <span class="flex min-w-0 items-center gap-2">
          <CircleCheck v-if="row.consent.given" class="size-4 shrink-0 text-success" aria-hidden="true" />
          <CircleDashed v-else class="size-4 shrink-0 text-on-night-secondary" aria-hidden="true" />
          <span class="min-w-0">
            {{ SHORT_TITLE[row.consent.type] }}
            <span v-if="row.companyName" class="text-on-night-secondary">· {{ row.companyName }}</span>
            <span v-if="!row.consent.required" class="text-on-night-secondary">· по желанию</span>
          </span>
        </span>
        <span v-if="row.consent.given" class="shrink-0 text-xs text-on-night-secondary">
          {{ row.consent.valid_until ? `до ${formatDate(row.consent.valid_until)}` : 'бессрочно' }}
        </span>
        <button
          v-else-if="row.canGive"
          type="button"
          class="shrink-0 rounded-lg bg-white/10 px-3 py-1 text-xs font-medium transition-colors hover:bg-white/20"
          @click="giving = row"
        >
          Дать
        </button>
        <span v-else class="shrink-0 text-xs text-on-night-secondary">даёт представитель</span>
      </li>
    </ul>

    <BaseModal v-model:open="modalOpen" :title="giving ? CONSENT_TEXT[giving.consent.type].title : ''" :description="giving?.consent.purpose">
      <PersonalConsentPrompt
        v-if="giving"
        :type="giving.consent.type"
        :organization-id="giving.organizationId"
        open
        @given="giving = null"
      />
    </BaseModal>
  </section>
</template>
