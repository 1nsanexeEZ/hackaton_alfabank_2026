<script setup lang="ts">
import { CircleAlert, CircleCheck, CircleHelp } from 'lucide-vue-next'
import { computed } from 'vue'

import type { OrganizationDetailDto } from '@/shared/api'
import { formatDate, formatDateTime, formatTerm } from '@/shared/lib'

/** Реквизиты из базы банка — клиенту их не вводить — и результат сверки с ЕГРЮЛ */
const props = defineProps<{ company: OrganizationDetailDto }>()

const LEGAL_FORM: Record<string, string> = { LLC: 'ООО', IE: 'ИП', JSC: 'АО' }
/** Как в clients/domain/value_objects.py TaxRegime */
const TAX_REGIME: Record<string, string> = { osn: 'ОСН', usn: 'УСН', ausn: 'АУСН', eshn: 'ЕСХН', patent: 'Патент' }
const FIELD: Record<string, string> = { head_name: 'Руководитель', name: 'Наименование', address: 'Адрес', kpp: 'КПП', okved_main: 'ОКВЭД' }

const rows = computed(() => {
  const company = props.company
  return [
    { label: 'Форма', value: LEGAL_FORM[company.legal_form] ?? company.legal_form },
    { label: 'ИНН', value: company.inn },
    { label: 'ОГРН', value: company.ogrn },
    ...(company.kpp ? [{ label: 'КПП', value: company.kpp }] : []),
    { label: 'Зарегистрирована', value: `${formatDate(company.registered_at)} · ${formatTerm(company.business_age_months)} работы` },
    { label: 'Адрес', value: company.address.full },
    { label: 'ОКВЭД', value: [company.okved_main, ...company.okved_extra].join(', ') },
    { label: 'Налоговый режим', value: TAX_REGIME[company.tax_regime] ?? company.tax_regime },
    { label: 'Сотрудников', value: String(company.employees_count) },
    ...(company.head_name ? [{ label: 'Руководитель по реестру', value: company.head_name }] : []),
  ]
})
</script>

<template>
  <section>
    <h3 class="text-base font-bold text-ink">Реквизиты</h3>
    <p class="mt-0.5 text-sm text-ink-secondary">Из базы банка — в заявке их вводить не нужно</p>

    <div
      class="mt-3 flex items-start gap-2 rounded-xl p-3 text-sm"
      :class="{
        'bg-success-soft text-ink': company.verification.status === 'verified',
        'bg-warning-soft text-ink': company.verification.status === 'mismatch',
        'bg-surface-soft text-ink-secondary': company.verification.status === 'unverified',
      }"
    >
      <CircleCheck v-if="company.verification.status === 'verified'" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
      <CircleAlert v-else-if="company.verification.status === 'mismatch'" class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
      <CircleHelp v-else class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div>
        <p v-if="company.verification.status === 'verified'">
          {{ company.verification.checked_at ? `Сверено с ЕГРЮЛ ${formatDateTime(company.verification.checked_at)}` : 'Сверено с ЕГРЮЛ' }}
        </p>
        <template v-else-if="company.verification.status === 'mismatch'">
          <p class="font-medium">Данные расходятся с ЕГРЮЛ — заявку посмотрит специалист банка</p>
          <ul class="mt-1 space-y-0.5 text-ink-secondary">
            <li v-for="item in company.verification.discrepancies" :key="item.field">
              {{ FIELD[item.field] ?? item.field }}: у нас «{{ item.declared ?? '—' }}», в реестре «{{ item.registry ?? '—' }}»
            </li>
          </ul>
        </template>
        <p v-else>Сверки с ЕГРЮЛ ещё не было</p>
      </div>
    </div>

    <dl class="mt-3 divide-y divide-line rounded-2xl bg-surface-soft px-4">
      <div v-for="row in rows" :key="row.label" class="flex justify-between gap-4 py-2.5 text-sm">
        <dt class="shrink-0 text-ink-secondary">{{ row.label }}</dt>
        <dd class="text-right font-medium text-ink">{{ row.value }}</dd>
      </div>
    </dl>
  </section>
</template>
