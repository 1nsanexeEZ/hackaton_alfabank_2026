<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import { computed } from 'vue'

import type { ApplicationDraft } from '@/entities/application'
import type { CreditProduct } from '@/entities/credit-product'
import { SECTION_ID, sectionHref } from '@/shared/config'
import { BaseBadge, BaseButton, BaseContainer, PatternBackground } from '@/shared/ui'

import { heroStats } from '../model/content'
import HeroApplication from './HeroApplication.vue'

const props = defineProps<{ products: readonly CreditProduct[] | null }>()

/** Куда вести «Оформить» и «Продолжить заявку», решает страница: виджет про поток заявки не знает */
const emit = defineEmits<{ apply: []; continue: [draft: ApplicationDraft]; open: [applicationId: string] }>()

const stats = computed(() => heroStats(props.products))
</script>

<template>
  <section class="hero relative flex flex-col justify-center overflow-hidden bg-night text-on-night">
    <PatternBackground />
    <div
      class="pointer-events-none absolute -top-48 right-[-40%] size-[28rem] rounded-full bg-brand/15 blur-[120px] lg:-top-40 lg:right-0 lg:size-[36rem] lg:bg-brand/25"
      aria-hidden="true"
    />
    <div
      class="pointer-events-none absolute bottom-0 left-[-10%] size-[28rem] rounded-full bg-info/15 blur-[120px]"
      aria-hidden="true"
    />

    <BaseContainer class="relative pt-8 pb-20 lg:pt-16 lg:pb-32">
      <div class="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-16">
        <div>
          <BaseBadge tone="glass">
            <Sparkles class="size-3.5" aria-hidden="true" />
            Предварительное решение онлайн
          </BaseBadge>
          <h1 class="text-display mt-5 max-w-2xl">
            Кредит для бизнеса — от заявки до решения в одном кабинете
          </h1>
          <p class="text-lead mt-5 max-w-xl text-on-night-secondary">
            Подберите продукт под задачу, рассчитайте платёж и следите за статусом заявки онлайн. Без визитов в
            офис и повторного ввода данных.
          </p>
          <div class="mt-8 flex flex-col gap-3 sm:flex-row">
            <BaseButton size="l" :href="sectionHref(SECTION_ID.products)">Подобрать кредит</BaseButton>
            <BaseButton size="l" variant="glass" :href="sectionHref(SECTION_ID.calculator)">
              Рассчитать платёж
            </BaseButton>
          </div>
        </div>

        <HeroApplication
          :products="products"
          class="w-full lg:justify-self-end"
          @apply="emit('apply')"
          @continue="(draft) => emit('continue', draft)"
          @open="(id) => emit('open', id)"
        />
      </div>

      <ul class="mt-12 grid grid-cols-2 gap-3 lg:mt-20 lg:grid-cols-4 lg:gap-4">
        <li
          v-for="stat in stats"
          :key="stat.caption"
          class="flex min-h-32 flex-col justify-between gap-4 rounded-3xl bg-night-glass p-4 lg:min-h-40 lg:rounded-card lg:p-6"
        >
          <div>
            <p v-if="stat.value" class="text-lg font-bold lg:text-2xl">{{ stat.value }}</p>
            <p v-else class="h-7 w-28 animate-pulse rounded-lg bg-white/10 lg:h-8" aria-label="Загружаем" />
            <p class="mt-1 text-sm text-on-night-secondary">{{ stat.caption }}</p>
          </div>
          <span class="flex size-10 items-center justify-center self-end rounded-full bg-white/10">
            <component :is="stat.icon" class="size-5" aria-hidden="true" />
          </span>
        </li>
      </ul>
    </BaseContainer>
  </section>
</template>

<style scoped>
/*
 * Hero занимает весь первый экран. Следующая секция наезжает на него
 * скруглённым листом на --r, поэтому добавляем эту высоту сверх экрана.
 */
.hero {
  --r: 2.5rem;
  /* Высота шапки */
  --header: 4rem;

  min-height: calc(100dvh - var(--header) + var(--r));
}

@media (width >= 64rem) {
  .hero {
    --r: var(--radius-sheet);
    --header: 4.5rem;
  }
}
</style>
