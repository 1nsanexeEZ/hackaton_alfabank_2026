<script setup lang="ts">
import { computed } from 'vue'

import { BaseBadge } from '@/shared/ui'

import type { CreditProduct } from '../model/types'

/**
 * Карточка-«гармошка» для витрины продуктов: в ряду раскрыта одна,
 * остальные свёрнуты в полоски с названием. Раскрытием управляет родитель.
 */
const props = defineProps<{
  product: CreditProduct
  /** Порядковый номер в ряду, с нуля — от него зависят номер и цвет карточки */
  index: number
  expanded: boolean
}>()

const emit = defineEmits<{ expand: [] }>()

const TONES = [
  'bg-brand text-white',
  'bg-night text-on-night',
  'bg-brand-active text-white',
  'bg-night-elevated text-on-night',
] as const

const tone = computed(() => TONES[props.index % TONES.length])
const number = computed(() => String(props.index + 1).padStart(2, '0'))
</script>

<template>
  <article
    class="flex-card relative overflow-hidden rounded-card"
    :class="[tone, { 'is-expanded': expanded }]"
  >
    <!-- Свёрнутая карточка целиком кликабельна -->
    <button
      v-if="!expanded"
      type="button"
      class="absolute inset-0 z-10 cursor-pointer"
      :aria-label="`Показать продукт «${product.title}»`"
      :aria-expanded="false"
      @click="emit('expand')"
    />

    <!-- Крупный номер — графический акцент вместо картинки -->
    <span
      class="flex-card__number pointer-events-none absolute font-bold leading-none select-none"
      aria-hidden="true"
    >
      {{ number }}
    </span>

    <!-- Подпись свёрнутой карточки -->
    <span class="flex-card__label pointer-events-none absolute font-semibold whitespace-nowrap">
      {{ product.title }}
    </span>

    <div class="flex-card__content relative flex h-full flex-col justify-end p-6 lg:p-8">
      <BaseBadge v-if="product.tag" tone="glass" class="self-start">{{ product.tag }}</BaseBadge>

      <h3 class="text-title mt-4">{{ product.title }}</h3>

      <ul class="mt-4 flex flex-wrap gap-2" aria-label="Коротко о продукте">
        <li
          v-for="word in product.keywords"
          :key="word"
          class="rounded-full bg-white/15 px-4 py-1.5 text-sm font-medium whitespace-nowrap"
        >
          {{ word }}
        </li>
      </ul>

      <div v-if="$slots.actions" class="mt-6 flex flex-col gap-3 sm:flex-row">
        <slot name="actions" />
      </div>
    </div>
  </article>
</template>

<style scoped>
.flex-card {
  --ease: cubic-bezier(0.05, 0.61, 0.41, 0.95);

  min-height: 4.5rem;
  transition:
    flex-grow 0.6s var(--ease),
    min-height 0.6s var(--ease),
    filter 0.3s;
}

.flex-card.is-expanded {
  min-height: 22rem;
}

.flex-card__number {
  top: 1.25rem;
  right: 1.5rem;
  font-size: 1.5rem;
  opacity: 0.5;
  transition:
    font-size 0.6s var(--ease),
    opacity 0.6s var(--ease);
}

.is-expanded .flex-card__number {
  font-size: 7rem;
  opacity: 0.15;
}

.flex-card__label {
  top: 50%;
  left: 1.5rem;
  translate: 0 -50%;
  font-size: 1.125rem;
  transition: opacity 0.3s;
}

.flex-card__content {
  opacity: 0;
  visibility: hidden;
  transition:
    opacity 0.3s,
    visibility 0s 0.3s;
}

/* Скрытый контент свёрнутой карточки не должен растягивать её по высоте */
.flex-card:not(.is-expanded) .flex-card__content {
  position: absolute;
  inset: auto 0 0;
}

.is-expanded .flex-card__label {
  opacity: 0;
}

.is-expanded .flex-card__content {
  opacity: 1;
  visibility: visible;
  transition:
    opacity 0.4s 0.25s,
    visibility 0s;
}

/* Десктоп: карточки в ряд, свёрнутые — узкие вертикальные полоски */
@media (width >= 64rem) {
  .flex-card {
    flex: 0 0 5.5rem;
    min-height: 0;
  }

  .flex-card.is-expanded {
    flex-grow: 1;
    min-height: 0;
  }

  .flex-card:not(.is-expanded):hover {
    filter: brightness(1.12);
  }

  .flex-card__number {
    top: auto;
    right: auto;
    bottom: 1.5rem;
    left: 50%;
    translate: -50% 0;
  }

  .is-expanded .flex-card__number {
    top: 1.5rem;
    right: 2rem;
    bottom: auto;
    left: auto;
    translate: none;
  }

  .flex-card__label {
    top: 2rem;
    left: 50%;
    translate: -50% 0;
    writing-mode: vertical-rl;
    rotate: 180deg;
  }

  .flex-card__content {
    /* Контент не сжимается вместе с карточкой, а уезжает за край */
    min-width: 30rem;
  }
}
</style>
