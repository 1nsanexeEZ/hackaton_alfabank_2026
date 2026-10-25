<script setup lang="ts">
import { ArrowLeft, Check, Radio, X } from 'lucide-vue-next'
import { computed } from 'vue'

import { CLIENT_STATUS_META } from '@/entities/application'
import type { ClientApplicationCardDto } from '@/shared/api'
import { formatMoney } from '@/shared/lib'

import { cardSteps, DARK_BADGE_CLASS, type StepState } from '../model/presentation'

/**
 * Тёмная шапка окна заявки: номер и статус, продукт и сумма, компания и этапы пути
 * «Подача → Проверка → Решение → Подписание → Выдача». Пока карточка грузится — только заголовок.
 * На телефоне этапы — полоса из пяти отрезков и название текущего.
 */
const props = defineProps<{
  card: ClientApplicationCardDto | null
  titleId: string
  /** Окно открыли из списка или уведомлений — кнопка «назад» */
  backLabel: string | null
  live: boolean
}>()

const emit = defineEmits<{ back: []; close: [] }>()

const meta = computed(() => (props.card ? CLIENT_STATUS_META[props.card.client_status] : null))

const title = computed(() => {
  const card = props.card
  if (!card) return 'Заявка'
  const amount = card.offer?.amount ?? card.request?.amount
  const product = card.product.name ?? card.product.code
  return amount ? `${product} · ${formatMoney(Number(amount))}` : product
})

const company = computed(() => {
  const organization = props.card?.organization
  return organization ? [organization.name, organization.inn && `ИНН ${organization.inn}`].filter(Boolean).join(' · ') : null
})

const steps = computed(() => (props.card ? cardSteps(props.card) : []))
const currentIndex = computed(() => steps.value.findIndex((step) => step.state !== 'done' && step.state !== 'todo'))
const current = computed(() => steps.value[currentIndex.value] ?? null)

const DOT_CLASS: Record<StepState, string> = {
  done: 'border-success bg-success',
  current: 'border-[3px] border-brand',
  failed: 'border-brand bg-brand',
  stopped: 'border-on-night-secondary',
  todo: 'border-night-line',
}

const BAR_CLASS: Record<StepState, string> = {
  done: 'bg-success',
  current: 'bg-brand',
  failed: 'bg-brand',
  stopped: 'bg-on-night-secondary',
  todo: 'bg-night-line',
}
</script>

<template>
  <header class="relative isolate shrink-0 overflow-hidden bg-night-elevated px-5 pt-5 pb-4 text-on-night sm:px-7 sm:pt-6 sm:pb-5">
    <!--
      Абстрактный фон: красное свечение из угла, тонкие кольца и красная линия по низу. Без него тёмная
      шапка сливалась с тёмными страницами (профиль, лендинг) под затемнением окна.
    -->
    <div class="card-header__decor pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
      <span class="card-header__ring card-header__ring--outer" />
      <span class="card-header__ring card-header__ring--inner" />
    </div>

    <div class="flex items-start gap-3.5">
      <span
        class="flex size-9 shrink-0 items-center justify-center rounded-[0.625rem] bg-brand text-xl font-black text-white sm:size-11 sm:rounded-xl sm:text-2xl"
        aria-hidden="true"
      >
        А
      </span>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <button
            v-if="backLabel"
            type="button"
            class="-ml-1 inline-flex items-center gap-1 rounded-md px-1 text-[0.8125rem] text-on-night-secondary transition-colors hover:text-on-night"
            @click="emit('back')"
          >
            <ArrowLeft class="size-3.5" aria-hidden="true" />
            {{ backLabel }}
          </button>
          <span v-if="card" class="text-[0.8125rem] tracking-wide text-on-night-secondary">Заявка {{ card.number }}</span>
          <span v-if="meta" class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="DARK_BADGE_CLASS[meta.tone]">
            {{ meta.label }}
          </span>
          <span
            v-if="live && card"
            class="inline-flex items-center gap-1 text-xs text-on-night-secondary"
            title="Статус обновляется сам, перезагружать страницу не нужно"
          >
            <Radio class="size-3.5 text-[#7fe0a6]" aria-hidden="true" />
            обновляется сам
          </span>
        </div>
        <h2 :id="titleId" class="mt-1 text-lg leading-tight font-extrabold tracking-tight sm:text-2xl">{{ title }}</h2>
        <p v-if="company" class="mt-1 truncate text-sm text-on-night-secondary">{{ company }}</p>
      </div>
      <button
        type="button"
        data-close
        class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-night-glass text-on-night transition-colors hover:bg-night-line"
        aria-label="Закрыть"
        @click="emit('close')"
      >
        <X class="size-5" aria-hidden="true" />
      </button>
    </div>

    <template v-if="steps.length">
      <!-- Телефон: полоса этапов и текущий этап словами -->
      <div class="mt-4 sm:hidden">
        <div class="grid grid-cols-5 gap-1" aria-hidden="true">
          <span v-for="step in steps" :key="step.label" class="h-1 rounded-full" :class="BAR_CLASS[step.state]" />
        </div>
        <p v-if="current" class="mt-2 flex justify-between text-[0.8125rem]">
          <span class="font-bold">{{ current.label }}<template v-if="current.note"> · {{ current.note }}</template></span>
          <span class="text-on-night-secondary">этап {{ currentIndex + 1 }} из {{ steps.length }}</span>
        </p>
        <p v-else class="mt-2 text-[0.8125rem] font-bold">Все этапы пройдены</p>
      </div>

      <!-- Шире телефона: все пять этапов с линиями между ними -->
      <ol class="mt-6 hidden grid-cols-5 sm:grid" aria-label="Этапы заявки">
        <li
          v-for="(step, index) in steps"
          :key="step.label"
          class="flex flex-col gap-2"
          :aria-current="step.state === 'current' ? 'step' : undefined"
        >
          <div class="flex items-center">
            <span class="flex size-[1.625rem] shrink-0 items-center justify-center rounded-full border-2" :class="DOT_CLASS[step.state]">
              <Check v-if="step.state === 'done'" class="size-3.5 stroke-[3] text-white" aria-hidden="true" />
              <span v-else-if="step.state === 'current'" class="size-2.5 rounded-full bg-brand" aria-hidden="true" />
              <X v-else-if="step.state === 'failed'" class="size-3.5 stroke-[3] text-white" aria-hidden="true" />
            </span>
            <span
              v-if="index < steps.length - 1"
              class="mx-2 h-0.5 flex-1 rounded-full"
              :class="step.state === 'done' ? 'bg-success' : 'bg-night-line'"
              aria-hidden="true"
            />
          </div>
          <span
            class="text-[0.8125rem]"
            :class="[
              step.state === 'current' || step.state === 'failed' ? 'font-bold text-on-night' : 'font-semibold',
              step.state === 'todo' ? 'text-on-night-secondary' : step.state === 'done' ? 'text-on-night/85' : '',
            ]"
          >
            {{ step.label }}
          </span>
          <span class="min-h-4 text-xs text-on-night-secondary">{{ step.note }}</span>
        </li>
      </ol>
    </template>
  </header>
</template>

<style scoped>
.card-header__decor {
  background:
    radial-gradient(70% 140% at 100% 0%, rgb(239 49 36 / 0.3), transparent 62%),
    radial-gradient(50% 90% at 0% 100%, rgb(31 98 214 / 0.14), transparent 70%);
}

/* Красная линия по низу: отделяет шапку от белого тела окна и держит фирменный акцент */
.card-header__decor::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--color-brand), rgb(239 49 36 / 0.25) 45%, transparent 75%);
}

.card-header__ring {
  position: absolute;
  border: 1px solid rgb(255 255 255 / 0.07);
  border-radius: 999px;
}

.card-header__ring--outer {
  top: -22rem;
  right: -12rem;
  width: 34rem;
  height: 34rem;
}

.card-header__ring--inner {
  top: -13rem;
  right: -5rem;
  width: 20rem;
  height: 20rem;
  border-color: rgb(255 255 255 / 0.09);
}
</style>
