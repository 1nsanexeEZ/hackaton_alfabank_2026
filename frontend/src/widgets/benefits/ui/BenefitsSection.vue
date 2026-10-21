<script setup lang="ts">
import { FileCheck2, ListChecks, Target, Zap } from 'lucide-vue-next'

import { BaseContainer, SectionHeader } from '@/shared/ui'

const BENEFITS = [
  {
    title: 'Подбор под задачу бизнеса',
    text: 'Подскажем продукт под цель: оборотные средства, оборудование, развитие или рефинансирование.',
    icon: Target,
    tone: 'sky',
  },
  {
    title: 'Решение онлайн',
    text: 'Проверку данных и оценку риска банк проводит автоматически, по простым заявкам — за минуты.',
    icon: Zap,
    tone: 'surface',
  },
  {
    title: 'Прозрачный статус',
    text: 'Видно, на каком этапе заявка, что сейчас делает банк и что нужно от вас.',
    icon: ListChecks,
    tone: 'surface',
  },
  {
    title: 'Без повторного ввода',
    text: 'Данные о компании подтягиваем из ЕГРЮЛ и ФНС, документы загружаются один раз.',
    icon: FileCheck2,
    tone: 'sky',
  },
] as const
</script>

<template>
  <section class="relative pt-2 pb-4 lg:pt-4">
    <BaseContainer>
      <SectionHeader
        title="Весь кредитный путь в одном кабинете"
        description="Кабинет связывает вас и банк: заявка, проверки, решение и подписание проходят в одном месте."
      />
      <ul class="mt-8 grid gap-4 md:grid-cols-2 lg:mt-12 lg:gap-6">
        <li
          v-for="benefit in BENEFITS"
          :key="benefit.title"
          class="flex items-start gap-5 rounded-card p-6 lg:p-8"
          :class="benefit.tone === 'sky' ? 'bg-sky' : 'bg-surface-soft'"
        >
          <div class="flex-1">
            <h3 class="text-subtitle text-ink">{{ benefit.title }}</h3>
            <p class="mt-2 text-ink-secondary">{{ benefit.text }}</p>
          </div>
          <span class="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-white text-brand shadow-sm">
            <component :is="benefit.icon" class="size-7" aria-hidden="true" />
          </span>
        </li>
      </ul>
    </BaseContainer>
  </section>
</template>
