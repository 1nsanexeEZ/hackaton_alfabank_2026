<script setup lang="ts">
import { Building2, Laptop } from 'lucide-vue-next'

import { BaseContainer, HintCard, SectionHeader } from '@/shared/ui'

import podborArt from '../assets/cabinet-1-podbor.svg'
import onlineArt from '../assets/cabinet-2-reshenie-online.svg'
import statusArt from '../assets/cabinet-3-prozrachnyj-status.svg'
import autofillArt from '../assets/cabinet-4-bez-povtornogo-vvoda.svg'

const BENEFITS = [
  {
    title: 'Подбор под задачу бизнеса',
    text: 'Подскажем продукт под цель: оборотные средства, оборудование, развитие или рефинансирование.',
    art: podborArt,
    tone: 'sky',
  },
  {
    title: 'Решение онлайн',
    text: 'Проверку данных и оценку риска банк проводит автоматически, по простым заявкам — за минуты.',
    art: onlineArt,
    tone: 'surface',
  },
  {
    title: 'Прозрачный статус',
    text: 'Видно, на каком этапе заявка, что сейчас делает банк и что нужно от вас.',
    art: statusArt,
    tone: 'surface',
  },
  {
    title: 'Без повторного ввода',
    text: 'Данные о компании подтягиваем по ИНН, документы загружаются один раз.',
    art: autofillArt,
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
            class="flex items-center gap-4 rounded-card p-6 lg:gap-6 lg:p-8"
            :class="benefit.tone === 'sky' ? 'bg-sky' : 'bg-surface-soft'"
          >
            <div class="flex-1">
              <h3 class="text-subtitle text-ink">{{ benefit.title }}</h3>
              <p class="mt-2 text-ink-secondary">{{ benefit.text }}</p>
            </div>
            <!-- Иллюстрация — украшение: смысл карточки в заголовке и тексте -->
            <img
              :src="benefit.art"
              alt=""
              width="400"
              height="400"
              loading="lazy"
              decoding="async"
              class="benefit-art -my-3 size-24 shrink-0 lg:-my-4 lg:size-32"
            />
          </li>
        </ul>
      </div>
    </BaseContainer>
  </section>
</template>
