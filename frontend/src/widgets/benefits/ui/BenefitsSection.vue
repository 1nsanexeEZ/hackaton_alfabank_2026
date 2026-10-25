<script setup lang="ts">
import { Building2, FileCheck2, Laptop, ListChecks, Target, Zap } from 'lucide-vue-next'

import { BaseContainer, HintCard, SectionHeader } from '@/shared/ui'

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
    text: 'Данные о компании подтягиваем по ИНН, документы загружаются один раз.',
    icon: FileCheck2,
    tone: 'sky',
  },
] as const
</script>

<template>
  <section class="relative bg-white pt-12 pb-4 lg:pt-20">
    <BaseContainer class="relative">
      <HintCard
        class="absolute top-0 right-6"
        :icon="Building2"
        tone="info"
        title="Данные по ИНН"
        caption="подтянули сами"
      />
      <HintCard
        class="absolute top-28 right-36"
        :icon="Laptop"
        tone="success"
        title="Без визита в офис"
        caption="всё в кабинете"
        :delay="2"
      />
      <SectionHeader
        title="Весь кредитный путь в одном кабинете"
        description="Кабинет связывает вас и банк: заявка, проверки, решение и подписание проходят в одном месте."
      />
      <div class="relative isolate mt-8 lg:mt-12">
        <ul class="grid gap-4 md:grid-cols-2 lg:gap-6">
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
      </div>
    </BaseContainer>
  </section>
</template>
