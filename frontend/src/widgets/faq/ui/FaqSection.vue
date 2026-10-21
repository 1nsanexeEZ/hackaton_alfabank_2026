<script setup lang="ts">
import { MessageCircleQuestion } from 'lucide-vue-next'
import { ref } from 'vue'

import { SECTION_ID } from '@/shared/config'
import { AccordionItem, BaseContainer, DecorSticker, PeekSticker, SectionHeader } from '@/shared/ui'

const QUESTIONS = [
  {
    question: 'Кто может подать заявку?',
    answer:
      'Индивидуальные предприниматели и компании малого бизнеса. Заявку может оформить собственник, директор, бухгалтер или другой сотрудник с полномочиями.',
  },
  {
    question: 'Какие данные понадобятся?',
    answer:
      'Для старта достаточно ИНН, суммы, срока и цели кредита. Сведения о компании банк получит из ЕГРЮЛ/ЕГРИП и ФНС. Если для решения нужны документы, банк запросит их в кабинете.',
  },
  {
    question: 'Как быстро банк примет решение?',
    answer:
      'Предварительное решение по простым заявкам — за несколько минут после автоматической проверки. Нестандартные заявки рассматривает кредитный аналитик, обычно в течение рабочего дня.',
  },
  {
    question: 'Чем скоринг отличается от решения по кредиту?',
    answer:
      'Скоринг оценивает уровень риска. Решение учитывает ещё продукт, сумму, срок и правила банка. Поэтому при одной оценке риска условия по разным продуктам могут отличаться.',
  },
  {
    question: 'Что будет, если банк предложит другие условия?',
    answer:
      'В кабинете появится контрпредложение: например, другая сумма или срок. Вы сможете принять его или отказаться — без новой заявки.',
  },
  {
    question: 'Как подписать договор?',
    answer:
      'После одобрения договор появится в кабинете. Подписание и выдача средств в прототипе смоделированы и не проводят реальных операций.',
  },
] as const

// Первый вопрос раскрыт, чтобы было понятно, что блок интерактивный
const openStates = ref(QUESTIONS.map((_, index) => index === 0))
</script>

<template>
  <section :id="SECTION_ID.faq" class="bg-surface-soft py-16 lg:py-24">
    <BaseContainer class="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-16">
      <SectionHeader
        title="Вопросы и ответы"
        description="Коротко о том, как устроен кредитный процесс."
        class="lg:sticky lg:top-28 lg:self-start"
      >
        <template #after>
          <DecorSticker
            class="mt-10 ml-4 w-max"
            :icon="MessageCircleQuestion"
            title="Остались вопросы?"
            caption="задайте их в кабинете"
            :tilt="-4"
          />
        </template>
      </SectionHeader>
      <div class="relative isolate">
        <PeekSticker art="question" class="absolute -top-16 right-12 -z-10" :tilt="12" :delay="1" />
        <div class="rounded-card bg-white px-6 py-2 lg:px-8">
          <AccordionItem
            v-for="(item, index) in QUESTIONS"
            :key="item.question"
            v-model:open="openStates[index]"
            :title="item.question"
            class="last:border-b-0"
          >
            {{ item.answer }}
          </AccordionItem>
        </div>
      </div>
    </BaseContainer>
  </section>
</template>
