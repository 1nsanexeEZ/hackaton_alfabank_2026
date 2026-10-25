<script setup lang="ts">
import { computed, reactive } from 'vue'

import { formatMoney } from '@/shared/lib'
import { BaseButton, SelectField, TextField } from '@/shared/ui'

import { PLAN_MONTHS, type BusinessPlanForm, type Guarantee } from '../model/useBusinessPlan'

/**
 * Бизнес-план и финмодель по шаблону банка: описание, кредит, свои средства, обеспечение, гарантия
 * господдержки и 24 месяца операционных выручки и расходов (без платежей по кредиту). Месяцы
 * заполняются разом — выручка первого месяца с ростом, расходы постоянные — и правятся по одному.
 */
defineProps<{ errors: Record<string, string>; saving: boolean; error: string | null; isNew: boolean }>()

const form = defineModel<BusinessPlanForm>('form', { required: true })

const emit = defineEmits<{ save: []; cancel: []; fill: [firstRevenue: number, growthPercent: number, expenses: number] }>()

const GUARANTEE_OPTIONS: readonly { value: Guarantee; label: string }[] = [
  { value: 'none', label: 'Без гарантии' },
  { value: 'msp_corporation', label: 'Корпорация МСП' },
  { value: 'regional_fund', label: 'Региональная гарантийная организация' },
]

const quick = reactive({ revenue: '', growth: '5', expenses: '' })
const toNumber = (value: string) => Number(value.replace(/\s/g, '').replace(',', '.'))
const canFill = computed(() => toNumber(quick.revenue) > 0 && toNumber(quick.expenses) >= 0 && quick.expenses.trim() !== '')

/** Итоги по годам — чтобы сразу видеть, сходится ли проект */
const years = computed(() =>
  [0, 1].map((year) => {
    const chunk = form.value.months.slice(year * 12, year * 12 + 12)
    const revenue = chunk.reduce((sum, month) => sum + (toNumber(month.revenue) || 0), 0)
    const expenses = chunk.reduce((sum, month) => sum + (toNumber(month.expenses) || 0), 0)
    return { title: `${year + 1}-й год`, revenue, expenses, flow: revenue - expenses }
  }),
)
</script>

<template>
  <form class="space-y-5" @submit.prevent="emit('save')">
    <label class="block">
      <span class="mb-2 block text-sm font-medium text-ink">Описание проекта</span>
      <textarea
        v-model="form.summary"
        rows="3"
        maxlength="2000"
        class="w-full rounded-lg bg-white px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-ink/20"
        :class="errors.summary && 'ring-2 ring-brand/40'"
        :aria-invalid="Boolean(errors.summary)"
        placeholder="Например: кофейня у метро — зерно от обжарщика, завтраки, доставка по району"
      />
      <span v-if="errors.summary" class="mt-1 block text-sm text-brand">{{ errors.summary }}</span>
    </label>

    <div class="grid gap-3 sm:grid-cols-3">
      <TextField v-model="form.loanAmount" filter="amount" label="Кредит, ₽" :error="errors.loanAmount" dense />
      <TextField v-model="form.loanTermMonths" filter="digits" label="Срок, мес." :error="errors.loanTermMonths" dense />
      <TextField v-model="form.ownFunds" filter="amount" label="Свои средства, ₽" :error="errors.ownFunds" dense />
    </div>

    <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
      <SelectField v-model="form.guarantee" label="Гарантия господдержки" :options="GUARANTEE_OPTIONS" dense />
      <TextField
        v-if="form.guarantee !== 'none'"
        v-model="form.guaranteePercent"
        label="Доля гарантии, %"
        inputmode="decimal"
        :error="errors.guaranteePercent"
        dense
      />
    </div>

    <div class="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
      <TextField v-model="form.collateralValue" filter="amount" label="Залог, ₽" hint="0 — без залога" :error="errors.collateralValue" dense />
      <TextField v-model="form.collateralDescription" label="Обеспечение" placeholder="Например: поручительство учредителя" dense />
    </div>

    <fieldset class="space-y-3 rounded-xl bg-white p-4">
      <legend class="sr-only">Финмодель по месяцам</legend>
      <p class="text-sm font-medium text-ink">Финмодель на {{ PLAN_MONTHS }} месяца от начала проекта</p>
      <p class="text-xs text-ink-secondary">Операционные выручка и расходы, без платежей по кредиту.</p>
      <div class="grid items-end gap-3 sm:grid-cols-[minmax(0,1fr)_7rem_minmax(0,1fr)_auto]">
        <TextField v-model="quick.revenue" filter="amount" label="Выручка в 1-й месяц, ₽" dense />
        <TextField v-model="quick.growth" filter="decimal" label="Рост в месяц, %" dense />
        <TextField v-model="quick.expenses" filter="amount" label="Расходы в месяц, ₽" dense />
        <BaseButton
          type="button"
          variant="secondary"
          size="s"
          :disabled="!canFill"
          @click="emit('fill', toNumber(quick.revenue), toNumber(quick.growth) || 0, toNumber(quick.expenses))"
        >
          Заполнить месяцы
        </BaseButton>
      </div>

      <ul class="grid gap-2 text-sm sm:grid-cols-2">
        <li v-for="year in years" :key="year.title" class="rounded-lg bg-surface-soft p-2.5">
          <p class="text-xs text-ink-secondary">{{ year.title }}</p>
          <p class="text-ink">
            выручка {{ formatMoney(year.revenue) }} · расходы {{ formatMoney(year.expenses) }}
          </p>
          <p class="text-xs" :class="year.flow > 0 ? 'text-success' : 'text-brand'">поток {{ formatMoney(year.flow) }}</p>
        </li>
      </ul>

      <details class="text-sm">
        <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">По месяцам — поправить вручную</summary>
        <div class="mt-2 max-h-80 overflow-y-auto">
          <table class="w-full text-left">
            <thead class="sticky top-0 bg-white text-xs text-ink-secondary">
              <tr>
                <th class="py-1.5 font-medium">Месяц</th>
                <th class="py-1.5 font-medium">Выручка, ₽</th>
                <th class="py-1.5 font-medium">Расходы, ₽</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(month, index) in form.months" :key="index">
                <td class="py-1 pr-2 text-ink-secondary tabular-nums">{{ index + 1 }}</td>
                <td class="py-1 pr-2">
                  <input
                    v-model="month.revenue"
                    inputmode="decimal"
                    :aria-label="`Выручка, ${index + 1}-й месяц`"
                    class="h-9 w-full rounded-lg bg-surface px-2 text-sm tabular-nums outline-none focus:bg-white focus:ring-2 focus:ring-ink/20"
                  />
                </td>
                <td class="py-1">
                  <input
                    v-model="month.expenses"
                    inputmode="decimal"
                    :aria-label="`Расходы, ${index + 1}-й месяц`"
                    class="h-9 w-full rounded-lg bg-surface px-2 text-sm tabular-nums outline-none focus:bg-white focus:ring-2 focus:ring-ink/20"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
      <p v-if="errors.months" class="text-sm text-brand">{{ errors.months }}</p>
    </fieldset>

    <p v-if="error" class="rounded-xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ error }}</p>
    <div class="flex flex-wrap gap-3">
      <BaseButton type="submit" :loading="saving">{{ isNew ? 'Сохранить план' : 'Сохранить изменения' }}</BaseButton>
      <BaseButton type="button" variant="ghost" :disabled="saving" @click="emit('cancel')">Отмена</BaseButton>
    </div>
  </form>
</template>
