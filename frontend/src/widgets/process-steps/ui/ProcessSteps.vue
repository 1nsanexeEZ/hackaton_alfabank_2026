<script setup lang="ts">
import { CircleCheck } from 'lucide-vue-next'

import { SECTION_ID } from '@/shared/config'
import { BaseBadge, BaseContainer, SectionHeader } from '@/shared/ui'

import productArt from '../assets/step-1-vyberite-produkt.svg'
import sendArt from '../assets/step-2-otpravte-zayavku.svg'
import checkArt from '../assets/step-3-proverka-dannyh.svg'
import decisionArt from '../assets/step-4-ocenka-i-reshenie.svg'
import signArt from '../assets/step-5-podpisanie-i-dengi.svg'

type Actor = 'client' | 'bank'

const ACTOR_LABEL: Record<Actor, string> = { client: 'Вы', bank: 'Банк' }

const STEPS: readonly { title: string; text: string; actor: Actor; art: string }[] = [
  {
    title: 'Выберите продукт',
    text: 'Сравните условия и рассчитайте платёж в калькуляторе.',
    actor: 'client',
    art: productArt,
  },
  {
    title: 'Отправьте заявку',
    text: 'Нужны только ИНН, сумма и цель. Данные о компании подтянутся автоматически.',
    actor: 'client',
    art: sendArt,
  },
  {
    title: 'Проверка данных',
    text: 'Банк сверяет сведения о компании и заявке по своим данным и открытым источникам.',
    actor: 'bank',
    art: checkArt,
  },
  {
    title: 'Оценка и решение',
    text: 'Скоринг оценивает риск, кредитная политика определяет условия. Если нужны документы — попросим в кабинете.',
    actor: 'bank',
    art: decisionArt,
  },
  {
    title: 'Подписание и деньги',
    text: 'Подпишите договор в кабинете, деньги поступят на расчётный счёт.',
    actor: 'client',
    art: signArt,
  },
]
</script>

<template>
  <section :id="SECTION_ID.process" class="py-16 lg:py-24">
    <BaseContainer class="relative">
      <!-- Чем заканчивается путь: уведомление о решении, как его покажет кабинет -->
      <div
        class="decision-card pointer-events-none absolute -top-6 right-8 hidden w-76 items-start gap-3 rounded-2xl bg-white p-4 shadow-[0_1.25rem_2.5rem_-1rem_rgb(20_20_30/0.25)] ring-1 ring-line select-none lg:flex"
        aria-hidden="true"
      >
        <span class="flex size-10 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
          <CircleCheck class="size-5" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="flex items-center justify-between gap-2 text-xs text-ink-secondary">
            Решение по заявке
            <span>только что</span>
          </p>
          <p class="mt-0.5 font-semibold text-ink">Кредит одобрен</p>
          <p class="mt-0.5 text-sm text-ink-secondary">5 000 000 ₽ · 36 мес. · от 18,9%</p>
        </div>
      </div>
      <SectionHeader
        title="Как проходит заявка"
        description="Каждый этап отражается в кабинете — вы всегда знаете, где заявка и что будет дальше."
      />
      <div class="relative isolate mt-8 lg:mt-12">
        <ol class="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <li
            v-for="(step, index) in STEPS"
            :key="step.title"
            class="flex flex-col rounded-3xl bg-surface-soft p-6 lg:rounded-card"
          >
            <div class="flex items-center justify-between gap-3">
              <span
                class="flex size-10 items-center justify-center rounded-full text-base font-bold"
                :class="step.actor === 'bank' ? 'bg-night text-on-night' : 'bg-brand text-white'"
              >
                {{ index + 1 }}
              </span>
              <BaseBadge :tone="step.actor === 'bank' ? 'neutral' : 'brand'">{{ ACTOR_LABEL[step.actor] }}</BaseBadge>
            </div>
            <img
              :src="step.art"
              alt=""
              width="400"
              height="400"
              loading="lazy"
              decoding="async"
              class="step-art mx-auto mt-2 size-32 lg:size-36"
            />
            <h3 class="mt-2 text-lg font-bold text-ink">{{ step.title }}</h3>
            <p class="mt-2 text-sm text-ink-secondary">{{ step.text }}</p>
          </li>
        </ol>
      </div>
    </BaseContainer>
  </section>
</template>

<style scoped>
/* Карточка решения слегка покачивается на месте — без наклонов и вспышек */
.decision-card {
  animation: decision-float 6s ease-in-out infinite;
}

@keyframes decision-float {
  50% {
    translate: 0 -0.375rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .decision-card {
    animation: none;
  }
}
</style>
