<script setup lang="ts">
import { AlertTriangle, CircleAlert, CircleCheck } from 'lucide-vue-next'
import { computed } from 'vue'

import { beneficialOwnersLine, countryName } from '@/entities/application'
import {
  AML_LIST_LABEL,
  AML_ROLE_LABEL,
  BENEFICIAL_BASIS_LABEL,
  OWNER_DISCREPANCY_LABEL,
  PEP_KIND_LABEL,
  ZSK_LEVEL_LABEL,
  type AmlRiskGroup,
} from '@/entities/underwriting'
import type { AmlCheckDto } from '@/shared/api'
import { formatDate } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

import SourceCard from './SourceCard.vue'

/**
 * Проверка по 115-ФЗ (enrichment.aml, docs/compliance-115.md): совпадение с перечнем Росфинмониторинга —
 * отказ, ПДЛ и средний риск ЗСК — проверка специалистом. Проверяются компания, учредители (юрлица цепочки
 * и физлица с любой долей), руководитель, бенефициары по ЕГРЮЛ и со слов клиента, представитель,
 * выгодоприобретатель и залогодатель. Группа риска клиента (policy_v9) — из трассы решения.
 * Бенефициары по ЕГРЮЛ и со слов клиента — рядом, расхождение между ними видно сразу.
 */
const props = defineProps<{ aml: AmlCheckDto; riskGroup: AmlRiskGroup | null }>()

const who = (subject: AmlCheckDto['subjects'][number]) => {
  const country = countryName(subject.country)
  return `${subject.name} (${AML_ROLE_LABEL[subject.role] ?? subject.role}${country ? `, ${country}` : ''})`
}
const ownerShare = (item: AmlCheckDto['beneficial_owners'][number]) =>
  item.share_percent ? `владение ${Number(item.share_percent)}%` : (BENEFICIAL_BASIS_LABEL[item.basis] ?? item.basis)

const mismatch = computed(() => Boolean(props.aml.owner_discrepancies?.length))
const clean = computed(() => !props.aml.list_hits.length && !props.aml.pep_hits.length)
</script>

<template>
  <SourceCard title="Проверка по 115-ФЗ" wide>
    <template #badges>
      <BaseBadge v-if="riskGroup" :tone="riskGroup.tone">Группа риска: {{ riskGroup.label }}</BaseBadge>
      <BaseBadge :tone="ZSK_LEVEL_LABEL[aml.zsk.level]?.tone ?? 'neutral'">Риск ЗСК: {{ ZSK_LEVEL_LABEL[aml.zsk.level]?.label ?? aml.zsk.level }}</BaseBadge>
      <BaseBadge v-if="aml.list_hits.length" tone="brand">Совпадение с перечнем</BaseBadge>
      <BaseBadge v-if="aml.pep_hits.length" tone="warning">ПДЛ</BaseBadge>
    </template>

    <p
      v-if="riskGroup && riskGroup.level !== 'low'"
      class="flex items-start gap-2.5 rounded-xl p-3 text-sm text-ink"
      :class="riskGroup.level === 'high' ? 'bg-warning-soft' : 'bg-surface-soft'"
      role="note"
    >
      <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
      <span><span class="font-semibold">Почему группа {{ riskGroup.label }}:</span> {{ riskGroup.factors }}</span>
    </p>

    <ul v-if="!clean" class="mt-2.5 space-y-1.5 text-sm">
      <li v-for="(hit, index) in aml.list_hits" :key="`list-${index}`" class="flex items-start gap-2 text-brand">
        <CircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ who(hit.subject) }} — {{ AML_LIST_LABEL[hit.list] ?? hit.list }}: {{ hit.record }}
      </li>
      <li v-for="(hit, index) in aml.pep_hits" :key="`pep-${index}`" class="flex items-start gap-2 text-warning">
        <CircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ who(hit.subject) }} — {{ PEP_KIND_LABEL[hit.kind] ?? hit.kind }}, {{ hit.position }}
      </li>
    </ul>

    <div class="mt-3 grid grid-cols-1 items-center gap-2.5 @lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
      <div class="min-w-0 rounded-xl bg-surface-soft px-3.5 py-3">
        <p class="text-xs text-ink-secondary">Бенефициары по ЕГРЮЛ</p>
        <template v-if="aml.beneficial_owners.length">
          <p v-for="item in aml.beneficial_owners" :key="item.name" class="mt-1 text-sm">
            <span class="font-semibold text-ink">{{ item.name }}</span>
            <span class="text-ink-secondary"> · {{ ownerShare(item) }}</span>
          </p>
        </template>
        <p v-else class="mt-1 text-sm text-ink-secondary">Не установлены</p>
      </div>
      <BaseBadge v-if="aml.declared_owners !== undefined" :tone="mismatch ? 'brand' : 'success'" class="justify-self-center">
        {{ mismatch ? '≠ расхождение' : '= совпадает' }}
      </BaseBadge>
      <div v-if="aml.declared_owners !== undefined" class="min-w-0 rounded-xl bg-surface-soft px-3.5 py-3">
        <p class="text-xs text-ink-secondary">Со слов клиента</p>
        <p class="mt-1 text-sm font-semibold text-ink">
          {{ aml.declared_owners ? beneficialOwnersLine({ owners: aml.declared_owners }) : 'Клиент не ответил' }}
        </p>
      </div>
    </div>
    <ul v-if="mismatch" class="mt-2 space-y-0.5 text-sm text-brand">
      <li v-for="item in aml.owner_discrepancies ?? []" :key="`${item.kind}-${item.name}`">
        {{ item.name }} — {{ OWNER_DISCREPANCY_LABEL[item.kind] ?? item.kind }}
      </li>
    </ul>

    <ul class="mt-3 grid grid-cols-1 gap-2 text-sm @lg:grid-cols-3">
      <li class="flex items-start gap-2">
        <CircleCheck v-if="clean" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        <CircleAlert v-else class="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
        <span>
          {{ clean ? 'Перечни и база ПДЛ — совпадений нет' : 'Есть совпадения с перечнями или ПДЛ' }}
          <span class="block text-xs text-ink-secondary">перечни на {{ formatDate(aml.lists_date) }}</span>
        </span>
      </li>
      <!-- licenses: null — реестр лицензий по заявке не запрашивали (старые заявки), строку не показываем -->
      <li v-if="aml.licenses" class="flex items-start gap-2">
        <CircleCheck class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        <span>
          {{ aml.licenses.length ? `Лицензий: ${aml.licenses.length}` : 'Лицензий в реестре нет' }}
          <span class="block text-xs text-ink-secondary">
            {{ aml.licenses.length ? aml.licenses.map((item) => `№ ${item.number}, ${item.activity} (ОКВЭД ${item.okved})`).join('; ') : 'реестр лицензий' }}
          </span>
        </span>
      </li>
      <li class="flex items-start gap-2">
        <CircleCheck class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
        <span>
          Проверено лиц: {{ aml.subjects.length }}
          <span class="block text-xs text-ink-secondary">ЗСК на {{ formatDate(aml.zsk.as_of) }}</span>
        </span>
      </li>
    </ul>
    <p class="mt-2 text-xs text-ink-secondary">Проверены: {{ aml.subjects.map(who).join(', ') }}</p>
  </SourceCard>
</template>
