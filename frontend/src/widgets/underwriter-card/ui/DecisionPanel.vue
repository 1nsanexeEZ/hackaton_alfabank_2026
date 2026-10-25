<script setup lang="ts">
import { AlertTriangle, CircleCheck, CircleX } from 'lucide-vue-next'
import { computed } from 'vue'

import { label, LIMIT_LABEL, OUTCOME_LABEL, REASON_LABEL, REVIEW_LABEL } from '@/entities/underwriting'
import type { DecisionDto, UnderwriterApplicationDto } from '@/shared/api'
import { formatDateTime, formatMoney, formatPercent, formatTerm } from '@/shared/lib'
import { BaseBadge, PanelCard } from '@/shared/ui'

import { amount, share } from '../model/figures'
import StatTile from './StatTile.vue'

/**
 * Решение движка: исход и причины сверху, затем лимит — запрос против итога и все расчётные лимиты полосами
 * (ограничивший — красным), затем ставка — составляющие полосой и коридор ставок продукта под ней.
 */
const props = defineProps<{ decision: DecisionDto; application: UnderwriterApplicationDto }>()

/** Лимиты по возрастанию; binding — тот, что дал итоговую сумму */
const limits = computed(() => {
  const value = props.decision.limits
  const rows = Object.entries(LIMIT_LABEL)
    .map(([key, title]) => ({ key, title, sum: amount(value[key as keyof typeof value] ?? null), binding: value.binding === key }))
    .filter((item): item is { key: string; title: string; sum: number; binding: boolean } => item.sum !== null)
    .sort((a, b) => a.sum - b.sum)
  const max = Math.max(1, ...rows.map((row) => row.sum))
  return rows.map((row) => ({ ...row, width: Math.max(2, share(row.sum, max)) }))
})
const finalLimit = computed(() => amount(props.decision.limits.final))
const bindingTitle = computed(() => (props.decision.limits.binding ? (LIMIT_LABEL[props.decision.limits.binding] ?? props.decision.limits.binding) : null))
const request = computed(() => amount(props.application.request?.amount))

/**
 * Ставка: составляющие складываются в расчётную, итог — в коридоре ставок продукта [rate_base; rate_max].
 * Шкала полосы — до большего из расчётной и потолка продукта.
 */
const RATE_PARTS = [
  { key: 'funding', title: 'Фондирование', color: 'bg-night' },
  { key: 'expected_loss', title: 'Ожидаемые потери', color: 'bg-warning' },
  { key: 'capital', title: 'Капитал', color: 'bg-info' },
  { key: 'margin', title: 'Маржа', color: 'bg-ink-muted' },
] as const
const rate = computed(() => {
  const breakdown = props.decision.rate_breakdown
  if (!breakdown) return null
  const parts = RATE_PARTS.map((part) => ({ ...part, value: Number(breakdown[part.key]) }))
  const raw = parts.reduce((sum, part) => sum + part.value, 0)
  const total = Number(breakdown.total)
  const floor = Number(props.application.product_terms.rate_base)
  const ceiling = Number(props.application.product_terms.rate_max)
  const scale = Math.max(raw, ceiling, total) * 1.04
  const clamped = Math.abs(raw - total) > 0.005
  return {
    parts: parts.map((part) => ({ ...part, width: share(part.value, scale) })),
    raw,
    total,
    floor,
    ceiling,
    corridor: { left: share(floor, scale), width: share(ceiling - floor, scale) },
    rawAt: share(raw, scale),
    note: clamped
      ? `расчётная ${formatPercent(raw)} ${raw > ceiling ? 'выше' : 'ниже'} коридора продукта ${formatPercent(floor)}–${formatPercent(ceiling)} → ${formatPercent(total)}`
      : `в коридоре продукта ${formatPercent(floor)}–${formatPercent(ceiling)}`,
  }
})

const matchedRules = computed(() => props.decision.rule_trace.filter((hit) => hit.matched).length)
</script>

<template>
  <PanelCard title="Решение движка">
    <div class="flex flex-wrap items-center gap-2">
      <BaseBadge :tone="OUTCOME_LABEL[decision.outcome]?.tone ?? 'neutral'">{{ OUTCOME_LABEL[decision.outcome]?.label ?? decision.outcome }}</BaseBadge>
      <BaseBadge v-if="decision.review" :tone="REVIEW_LABEL[decision.review].tone">{{ REVIEW_LABEL[decision.review].label }}</BaseBadge>
      <span class="text-xs text-ink-secondary">
        {{ decision.decided_by_type === 'auto' ? 'автоматически' : 'андеррайтер' }} · {{ formatDateTime(decision.decided_at) }}
      </span>
    </div>
    <p v-if="decision.override_of" class="mt-2 rounded-xl bg-info-soft p-2.5 text-xs text-ink">
      Решение андеррайтера заменило автоматическое: в журнале остались оба, действует это
    </p>

    <ul v-if="decision.reason_codes.length" class="mt-3 space-y-1.5 rounded-xl bg-warning-soft p-3 text-sm text-ink">
      <li v-for="code in decision.reason_codes" :key="code" class="flex items-start gap-2">
        <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
        <span class="font-semibold">{{ label(REASON_LABEL, code) }}</span>
      </li>
    </ul>
    <div v-if="decision.triggers?.length" class="mt-2 rounded-xl bg-warning-soft p-3 text-sm">
      <p class="text-xs font-semibold text-ink">Сработали триггеры ручной проверки</p>
      <ul class="mt-1 space-y-0.5 text-ink">
        <li v-for="trigger in decision.triggers" :key="trigger.code">• {{ trigger.detail }}</li>
      </ul>
    </div>

    <div v-if="decision.terms" class="mt-3 grid grid-cols-2 gap-2.5">
      <StatTile label="Сумма" :hint="`на ${formatTerm(decision.terms.term_months)}`">{{ formatMoney(Number(decision.terms.amount)) }}</StatTile>
      <StatTile label="Ставка" :hint="`платёж ${formatMoney(Number(decision.terms.monthly_payment))}`">{{ formatPercent(Number(decision.terms.rate)) }}</StatTile>
    </div>

    <template v-if="limits.length">
      <h3 class="mt-5 text-xs font-bold tracking-wide text-ink-secondary uppercase">Лимит</h3>
      <p v-if="finalLimit !== null" class="mt-1 text-2xl font-extrabold text-ink tabular-nums">{{ formatMoney(finalLimit) }}</p>
      <p v-if="bindingTitle" class="text-xs text-ink-secondary">ограничил расчёт «{{ bindingTitle.toLowerCase() }}»</p>
      <div v-if="request !== null && finalLimit" class="mt-2.5">
        <div class="flex justify-between gap-2 text-xs">
          <span class="text-ink">Запрос {{ formatMoney(request) }}</span>
          <span class="font-semibold" :class="request <= finalLimit ? 'text-success' : 'text-brand'">
            {{ request <= finalLimit ? `${Math.round((request / finalLimit) * 100)}% лимита` : 'выше лимита' }}
          </span>
        </div>
        <div class="mt-1 h-2.5 overflow-hidden rounded-full bg-surface-strong" role="img" :aria-label="`Запрос — ${Math.round((request / finalLimit) * 100)}% итогового лимита`">
          <div class="h-full rounded-full" :class="request <= finalLimit ? 'bg-night' : 'bg-brand'" :style="{ width: `${share(request, finalLimit)}%` }" />
        </div>
      </div>
      <ul class="mt-3 space-y-2">
        <li v-for="item in limits" :key="item.key">
          <div class="flex justify-between gap-3 text-xs" :class="item.binding ? 'font-bold text-brand' : 'text-ink-secondary'">
            <span>{{ item.title }}<template v-if="item.binding"> — ограничил</template></span>
            <span class="tabular-nums">{{ formatMoney(item.sum) }}</span>
          </div>
          <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-surface" aria-hidden="true">
            <div class="h-full rounded-full" :class="item.binding ? 'bg-brand' : 'bg-surface-strong'" :style="{ width: `${item.width}%` }" />
          </div>
        </li>
      </ul>
    </template>

    <template v-if="rate">
      <h3 class="mt-5 text-xs font-bold tracking-wide text-ink-secondary uppercase">Ставка</h3>
      <p class="mt-1 text-2xl font-extrabold text-ink tabular-nums">{{ formatPercent(rate.total) }}</p>
      <p class="text-xs text-ink-secondary">{{ rate.note }}</p>
      <div class="mt-3">
        <div
          class="flex h-3.5 overflow-hidden rounded"
          role="img"
          :aria-label="`Составляющие ставки: ${rate.parts.map((part) => `${part.title.toLowerCase()} ${formatPercent(part.value)}`).join(', ')}`"
        >
          <span v-for="part in rate.parts" :key="part.key" :class="part.color" class="min-w-[3px]" :style="{ width: `${part.width}%` }" />
        </div>
        <div class="relative mt-1 h-6 text-[11px] tabular-nums" aria-hidden="true">
          <span class="absolute top-0 h-1.5 rounded-sm border border-success bg-success-soft" :style="{ left: `${rate.corridor.left}%`, width: `${rate.corridor.width}%` }" />
          <span class="absolute top-2 -translate-x-1/2 text-success" :style="{ left: `${rate.corridor.left}%` }">{{ formatPercent(rate.floor) }}</span>
          <span class="absolute top-2 -translate-x-1/2 text-success" :style="{ left: `${rate.corridor.left + rate.corridor.width}%` }">{{ formatPercent(rate.ceiling) }}</span>
          <span v-if="Math.abs(rate.raw - rate.ceiling) > 1 && Math.abs(rate.raw - rate.floor) > 1" class="absolute top-2 -translate-x-1/2 text-ink-secondary" :style="{ left: `${Math.min(96, rate.rawAt)}%` }">
            {{ formatPercent(rate.raw) }}
          </span>
        </div>
      </div>
      <dl class="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div v-for="part in rate.parts" :key="part.key" class="flex items-center justify-between gap-2">
          <dt class="flex items-center gap-1.5 text-ink-secondary"><span class="size-2.5 rounded-sm" :class="part.color" aria-hidden="true" />{{ part.title }}</dt>
          <dd class="font-semibold text-ink tabular-nums">{{ formatPercent(part.value) }}</dd>
        </div>
      </dl>
    </template>

    <p class="mt-4 text-xs text-ink-secondary">Политика {{ decision.policy_version }} · ключевая ставка {{ formatPercent(Number(decision.key_rate)) }}</p>
    <details class="mt-3 text-sm">
      <summary class="cursor-pointer rounded-xl bg-surface-soft px-3.5 py-2.5 font-semibold text-ink hover:bg-surface">
        Как движок пришёл к решению · правил {{ decision.rule_trace.length }}, сработали {{ matchedRules }}
      </summary>
      <ul class="mt-2 space-y-1.5">
        <li v-for="(hit, index) in decision.rule_trace" :key="index" class="flex items-start gap-2" :class="!hit.matched && 'text-ink-muted'">
          <CircleCheck v-if="hit.matched" class="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          <CircleX v-else class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{{ hit.detail }} <span class="text-xs text-ink-muted">({{ hit.rule }})</span></span>
        </li>
      </ul>
    </details>
  </PanelCard>
</template>
