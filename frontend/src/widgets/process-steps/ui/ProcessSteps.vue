<script setup lang="ts">
import { SECTION_ID } from '@/shared/config'
import { BaseBadge, BaseContainer, DecorSticker, PeekSticker, SectionHeader } from '@/shared/ui'

type Actor = 'client' | 'bank'

const ACTOR_LABEL: Record<Actor, string> = { client: 'Вы', bank: 'Банк' }

const STEPS: readonly { title: string; text: string; actor: Actor }[] = [
  {
    title: 'Выберите продукт',
    text: 'Сравните условия и рассчитайте платёж в калькуляторе.',
    actor: 'client',
  },
  {
    title: 'Отправьте заявку',
    text: 'Нужны только ИНН, сумма и цель. Данные о компании подтянутся автоматически.',
    actor: 'client',
  },
  {
    title: 'Проверка данных',
    text: 'Банк сверяет сведения с ЕГРЮЛ/ЕГРИП, ФНС и бюро кредитных историй.',
    actor: 'bank',
  },
  {
    title: 'Оценка и решение',
    text: 'Скоринг оценивает риск, кредитная политика определяет условия. Если нужны документы — попросим в кабинете.',
    actor: 'bank',
  },
  {
    title: 'Подписание и деньги',
    text: 'Подпишите договор в кабинете, деньги поступят на расчётный счёт.',
    actor: 'client',
  },
]
</script>

<template>
  <section :id="SECTION_ID.process" class="py-16 lg:py-24">
    <BaseContainer class="relative">
      <DecorSticker class="absolute -top-10 right-16" burst tone="sun" title="Одобрено!" caption="кредит" :tilt="-12" />
      <SectionHeader
        title="Как проходит заявка"
        description="Каждый этап отражается в кабинете — вы всегда знаете, где заявка и что будет дальше."
      />
      <div class="relative isolate mt-8 lg:mt-12">
        <PeekSticker art="piggy" from="bottom" class="absolute -right-6 -bottom-16 -z-10" :tilt="-8" :delay="2" />
        <PeekSticker art="chart" class="absolute -top-16 left-[42%] -z-10" :tilt="-10" :delay="4" />
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
            <h3 class="mt-6 text-lg font-bold text-ink">{{ step.title }}</h3>
            <p class="mt-2 text-sm text-ink-secondary">{{ step.text }}</p>
          </li>
        </ol>
      </div>
    </BaseContainer>
  </section>
</template>
