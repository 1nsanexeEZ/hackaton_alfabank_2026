<script setup lang="ts">
import { AML_LIST_LABEL, AML_ROLE_LABEL, BENEFICIAL_BASIS_LABEL, PEP_KIND_LABEL, ZSK_LEVEL_LABEL } from '@/entities/underwriting'
import type { AmlCheckDto } from '@/shared/api'
import { formatDate } from '@/shared/lib'
import { BaseBadge } from '@/shared/ui'

/**
 * Проверка по 115-ФЗ (enrichment.aml, docs/compliance-115.md): совпадение с перечнем Росфинмониторинга —
 * отказ, ПДЛ и средний риск ЗСК — проверка специалистом. Проверяются компания, учредители-юрлица цепочки,
 * руководитель, бенефициары и представитель, который подал заявку.
 */
defineProps<{ aml: AmlCheckDto }>()

const who = (subject: AmlCheckDto['subjects'][number]) => `${subject.name} (${AML_ROLE_LABEL[subject.role] ?? subject.role})`
const owner = (item: AmlCheckDto['beneficial_owners'][number]) =>
  `${item.name} (${item.share_percent ? `${Number(item.share_percent)}%` : (BENEFICIAL_BASIS_LABEL[item.basis] ?? item.basis)})`
</script>

<template>
  <section class="text-sm lg:col-span-2">
    <p class="flex flex-wrap items-center gap-2 font-semibold text-ink">
      Проверка по 115-ФЗ
      <BaseBadge :tone="ZSK_LEVEL_LABEL[aml.zsk.level]?.tone ?? 'neutral'">риск ЗСК: {{ ZSK_LEVEL_LABEL[aml.zsk.level]?.label ?? aml.zsk.level }}</BaseBadge>
      <BaseBadge v-if="aml.list_hits.length" tone="brand">совпадение с перечнем</BaseBadge>
      <BaseBadge v-if="aml.pep_hits.length" tone="warning">ПДЛ</BaseBadge>
    </p>
    <ul class="mt-2 space-y-1 text-ink">
      <li v-for="(hit, index) in aml.list_hits" :key="`list-${index}`" class="text-brand">
        {{ who(hit.subject) }} — {{ AML_LIST_LABEL[hit.list] ?? hit.list }}: {{ hit.record }}
      </li>
      <li v-for="(hit, index) in aml.pep_hits" :key="`pep-${index}`" class="text-warning">
        {{ who(hit.subject) }} — {{ PEP_KIND_LABEL[hit.kind] ?? hit.kind }}, {{ hit.position }}
      </li>
      <li v-if="!aml.list_hits.length && !aml.pep_hits.length">Совпадений с перечнями и базой ПДЛ нет</li>
      <li v-if="aml.beneficial_owners.length">
        Бенефициары: {{ aml.beneficial_owners.map(owner).join(', ') }}
      </li>
    </ul>
    <p class="mt-1 text-xs text-ink-secondary">
      Проверены: {{ aml.subjects.map(who).join(', ') }} · перечни на {{ formatDate(aml.lists_date) }}, ЗСК на {{ formatDate(aml.zsk.as_of) }}
    </p>
  </section>
</template>
