<script setup lang="ts">
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

/**
 * Проверка по 115-ФЗ (enrichment.aml, docs/compliance-115.md): совпадение с перечнем Росфинмониторинга —
 * отказ, ПДЛ и средний риск ЗСК — проверка специалистом. Проверяются компания, учредители (юрлица цепочки
 * и физлица с любой долей), руководитель, бенефициары по ЕГРЮЛ и со слов клиента, представитель,
 * выгодоприобретатель и залогодатель. Группа риска клиента (policy_v9) — из трассы решения.
 */
defineProps<{ aml: AmlCheckDto; riskGroup: AmlRiskGroup | null }>()

const who = (subject: AmlCheckDto['subjects'][number]) => {
  const country = countryName(subject.country)
  return `${subject.name} (${AML_ROLE_LABEL[subject.role] ?? subject.role}${country ? `, ${country}` : ''})`
}
const owner = (item: AmlCheckDto['beneficial_owners'][number]) =>
  `${item.name} (${item.share_percent ? `${Number(item.share_percent)}%` : (BENEFICIAL_BASIS_LABEL[item.basis] ?? item.basis)})`
</script>

<template>
  <section class="text-sm lg:col-span-2">
    <p class="flex flex-wrap items-center gap-2 font-semibold text-ink">
      Проверка по 115-ФЗ
      <BaseBadge v-if="riskGroup" :tone="riskGroup.tone">группа риска: {{ riskGroup.label }}</BaseBadge>
      <BaseBadge :tone="ZSK_LEVEL_LABEL[aml.zsk.level]?.tone ?? 'neutral'">риск ЗСК: {{ ZSK_LEVEL_LABEL[aml.zsk.level]?.label ?? aml.zsk.level }}</BaseBadge>
      <BaseBadge v-if="aml.list_hits.length" tone="brand">совпадение с перечнем</BaseBadge>
      <BaseBadge v-if="aml.pep_hits.length" tone="warning">ПДЛ</BaseBadge>
    </p>
    <p v-if="riskGroup" class="mt-1 text-xs" :class="riskGroup.level === 'low' ? 'text-ink-secondary' : 'text-ink'">
      Группа риска по факторам: {{ riskGroup.factors }}
    </p>
    <ul class="mt-2 space-y-1 text-ink">
      <li v-for="(hit, index) in aml.list_hits" :key="`list-${index}`" class="text-brand">
        {{ who(hit.subject) }} — {{ AML_LIST_LABEL[hit.list] ?? hit.list }}: {{ hit.record }}
      </li>
      <li v-for="(hit, index) in aml.pep_hits" :key="`pep-${index}`" class="text-warning">
        {{ who(hit.subject) }} — {{ PEP_KIND_LABEL[hit.kind] ?? hit.kind }}, {{ hit.position }}
      </li>
      <li v-if="!aml.list_hits.length && !aml.pep_hits.length">Совпадений с перечнями и базой ПДЛ нет</li>
      <li v-if="aml.beneficial_owners.length">Бенефициары по ЕГРЮЛ: {{ aml.beneficial_owners.map(owner).join(', ') }}</li>
      <li v-if="aml.declared_owners !== undefined">
        Бенефициары со слов клиента: {{ aml.declared_owners ? beneficialOwnersLine({ owners: aml.declared_owners }) : 'клиент не ответил' }}
      </li>
      <li v-for="item in aml.owner_discrepancies ?? []" :key="`${item.kind}-${item.name}`" class="text-brand">
        Расхождение: {{ item.name }} — {{ OWNER_DISCREPANCY_LABEL[item.kind] ?? item.kind }}
      </li>
      <!-- licenses: null — реестр лицензий по заявке не запрашивали (старые заявки), строку не показываем -->
      <li v-if="aml.licenses">
        Лицензии:
        {{ aml.licenses.length ? aml.licenses.map((item) => `№ ${item.number}, ${item.activity} (ОКВЭД ${item.okved})`).join('; ') : 'нет' }}
      </li>
    </ul>
    <p class="mt-1 text-xs text-ink-secondary">
      Проверены: {{ aml.subjects.map(who).join(', ') }} · перечни на {{ formatDate(aml.lists_date) }}, ЗСК на {{ formatDate(aml.zsk.as_of) }}
    </p>
  </section>
</template>
