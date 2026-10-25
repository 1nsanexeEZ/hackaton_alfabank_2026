<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'

import { BaseBadge } from '@/shared/ui'

import { productArt } from '../model/art'
import type { CreditProduct } from '../model/types'

/**
 * Карточка-«гармошка» для витрины продуктов: в ряду раскрыта одна,
 * остальные свёрнуты в полоски с названием. Раскрытием управляет родитель.
 *
 * Движение подсказывает, что карточки кликабельные: свёрнутые по очереди подпрыгивают
 * «волной», стрелка на них подталкивается, при наведении карточка приподнимается.
 * У раскрытой внизу бежит полоса автопрокрутки; когда она доходит до конца — событие `finished`.
 */
const props = withDefaults(
  defineProps<{
    product: CreditProduct
    /** Порядковый номер в ряду, с нуля — от него зависят номер, цвет и задержка волны */
    index: number
    expanded: boolean
    /** Длительность полосы автопрокрутки, мс; 0 — полосы нет */
    autoplayMs?: number
    /** Пауза полосы и волны: курсор над рядом или блок вне экрана */
    paused?: boolean
  }>(),
  { autoplayMs: 0, paused: false },
)

const emit = defineEmits<{ expand: []; finished: [] }>()

const TONES = [
  'bg-brand text-white',
  'bg-night text-on-night',
  'bg-brand-active text-white',
  'bg-night-elevated text-on-night',
] as const

const tone = computed(() => TONES[props.index % TONES.length])
const number = computed(() => String(props.index + 1).padStart(2, '0'))
const art = computed(() => productArt(props.product.code))
</script>

<template>
  <article
    class="flex-card relative overflow-hidden rounded-card"
    :class="[tone, { 'is-expanded': expanded, 'is-paused': paused }]"
    :style="{ '--wave-delay': `${index * 0.35}s` }"
  >
    <!-- Свёрнутая карточка целиком кликабельна -->
    <button
      v-if="!expanded"
      type="button"
      class="flex-card__cover absolute inset-0 z-10 cursor-pointer"
      :aria-label="`Показать продукт «${product.title}»`"
      :aria-expanded="false"
      @click="emit('expand')"
    />

    <!-- Крупный номер — графический акцент; у раскрытой карточки он слева, справа — иллюстрация продукта -->
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

    <!-- Стрелка-приглашение на свёрнутой карточке -->
    <span
      class="flex-card__hint pointer-events-none absolute hidden size-10 items-center justify-center rounded-full bg-white/15 lg:flex"
      aria-hidden="true"
    >
      <ChevronRight class="flex-card__chevron size-[18px]" :stroke-width="2.6" />
    </span>

    <div class="flex-card__content relative flex h-full flex-col justify-end p-6 lg:p-8">
      <!-- Иллюстрация — украшение: продукт назван в заголовке. Одного размера у всех продуктов, текст её не сжимает -->
      <img
        v-if="art"
        :src="art"
        alt=""
        width="400"
        height="400"
        decoding="async"
        class="flex-card__art"
      />
      <BaseBadge v-if="product.tag" tone="glass" class="flex-card__rise self-start">{{ product.tag }}</BaseBadge>

      <h3 class="flex-card__rise text-title mt-4" style="--rise-delay: 0.05s">{{ product.title }}</h3>

      <ul class="mt-4 flex flex-wrap gap-2" aria-label="Коротко о продукте">
        <li
          v-for="(word, wordIndex) in product.keywords"
          :key="word"
          class="flex-card__rise rounded-full bg-white/15 px-4 py-1.5 text-sm font-medium whitespace-nowrap"
          :style="{ '--rise-delay': `${0.12 + wordIndex * 0.07}s` }"
        >
          {{ word }}
        </li>
      </ul>

      <div v-if="$slots.actions" class="flex-card__rise mt-6 flex flex-col gap-3 sm:flex-row" style="--rise-delay: 0.3s">
        <slot name="actions" />
      </div>
    </div>

    <!-- Полоса автопрокрутки: CSS-анимация, её конец переключает карточку -->
    <span
      v-if="expanded && autoplayMs"
      class="flex-card__track pointer-events-none absolute right-8 bottom-3.5 left-8 hidden h-[3px] overflow-hidden rounded-full bg-white/20 lg:block"
      aria-hidden="true"
    >
      <span
        class="flex-card__progress block h-full rounded-full bg-white"
        :style="{ animationDuration: `${autoplayMs}ms` }"
        @animationend="emit('finished')"
      />
    </span>
  </article>
</template>

<style scoped>
.flex-card {
  --ease: cubic-bezier(0.05, 0.61, 0.41, 0.95);
  --spring: cubic-bezier(0.22, 1, 0.36, 1);

  /* Картинка подстраивается под ширину карточки: у широкой раскрытой она крупнее */
  container-type: inline-size;
  min-height: 4.5rem;
  transition:
    flex-grow 0.6s var(--ease),
    flex-basis 0.5s var(--spring),
    min-height 0.6s var(--ease),
    translate 0.35s ease,
    box-shadow 0.35s ease,
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
  right: auto;
  left: 1.5rem;
  font-size: 7rem;
  opacity: 0.15;
}

/* Телефон: картинка над текстом сверху справа, одного размера у всех — карточка подрастает под текст */
.flex-card__art {
  flex: none;
  align-self: flex-end;
  width: 9rem;
  height: 9rem;
  margin: -0.5rem -0.5rem auto 0;
  object-fit: contain;
}

/* Иллюстрация чуть покачивается на месте, пока карточка раскрыта */
.is-expanded .flex-card__art {
  animation:
    flex-card-rise 0.6s var(--spring) both 0.25s,
    flex-card-float 6s ease-in-out infinite 0.85s;
}

.is-paused .flex-card__art {
  animation-play-state: running, paused;
}

@keyframes flex-card-float {
  50% {
    translate: 0 -0.5rem;
  }
}

.flex-card__label {
  top: 50%;
  left: 1.5rem;
  translate: 0 -50%;
  font-size: 1.125rem;
  transition: opacity 0.3s;
}

.flex-card__hint {
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

.is-expanded .flex-card__label,
.is-expanded .flex-card__hint {
  opacity: 0;
}

.is-expanded .flex-card__content {
  opacity: 1;
  visibility: visible;
  transition:
    opacity 0.4s 0.25s,
    visibility 0s;
}

/* Содержимое раскрытой карточки поднимается по очереди */
.is-expanded .flex-card__rise {
  animation: flex-card-rise 0.6s var(--spring) both;
  animation-delay: calc(0.25s + var(--rise-delay, 0s));
}

@keyframes flex-card-rise {
  from {
    opacity: 0;
    transform: translateY(1.5rem);
  }
}

.flex-card__progress {
  transform-origin: left;
  animation: flex-card-progress linear both;
}

.is-paused .flex-card__progress {
  animation-play-state: paused;
}

@keyframes flex-card-progress {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}

.flex-card__cover:focus-visible {
  outline: 3px solid white;
  outline-offset: -6px;
  border-radius: inherit;
}

/* Десктоп: карточки в ряд, свёрнутые — узкие вертикальные полоски */
@media (width >= 64rem) {
  .flex-card {
    flex: 0 0 5.5rem;
    min-height: 0;
  }

  /*
   * Раскрытая забирает всё свободное место ряда. Ряд-окно задаёт ей точную ширину:
   * --flex-card-expanded-w и --flex-card-expanded-grow: 0, чтобы длинный заголовок её не растягивал.
   */
  .flex-card.is-expanded {
    flex: var(--flex-card-expanded-grow, 1) 0 var(--flex-card-expanded-w, 5.5rem);
    min-height: 0;
  }

  /* Наведение только приподнимает полоску: ширины в ряду не меняются, соседей не трясёт */
  .flex-card:not(.is-expanded):hover {
    translate: 0 -0.5rem;
    box-shadow: 0 1.5rem 2.5rem rgb(18 18 19 / 0.22);
    filter: brightness(1.12);
  }

  /* Волна: свёрнутые карточки по очереди подпрыгивают, пока ряд не трогают */
  .flex-card:not(.is-expanded, .is-paused) {
    animation: flex-card-wave 7s ease-in-out infinite;
    animation-delay: var(--wave-delay);
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
    right: auto;
    bottom: auto;
    left: 2rem;
    translate: none;
    animation: flex-card-number 0.8s var(--spring) both;
  }

  /* Подпись — от верха до стрелки; длинное название не наезжает на неё, а обрезается */
  .flex-card__label {
    top: 2rem;
    left: 50%;
    max-height: calc(100% - 10rem);
    overflow: hidden;
    text-overflow: ellipsis;
    translate: -50% 0;
    writing-mode: vertical-rl;
    rotate: 180deg;
  }

  /* Стрелка — над номером внизу */
  .flex-card__hint {
    bottom: 4.5rem;
    left: 50%;
    translate: -50% 0;
    animation: flex-card-ring 2.2s ease-out infinite;
  }

  .flex-card__chevron {
    animation: flex-card-nudge 1.6s ease-in-out infinite;
  }

  .flex-card__content {
    /* Контент не сжимается вместе с карточкой, а уезжает за край */
    min-width: 30rem;
    /* Свой слой: картинка с z-index −1 уходит под текст, но не под фон карточки */
    isolation: isolate;
  }

  /*
   * Ряд фиксированной высоты: картинка не в потоке, а в правом верхнем углу — длинный заголовок
   * или метка её не сжимают. Под текстом (z-index −1): если тексту тесно, он поверх.
   */
  .flex-card__art {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    z-index: -1;
    width: 11.5rem;
    height: 11.5rem;
    margin: 0;
    transition:
      top 0.5s var(--spring),
      right 0.5s var(--spring),
      width 0.5s var(--spring),
      height 0.5s var(--spring);
  }

  /* Широкая раскрытая карточка — в ряду два-три продукта: картинка крупно справа по центру */
  @container (width >= 48rem) {
    .flex-card__art {
      top: calc(50% - 10rem);
      right: 3rem;
      width: 20rem;
      height: 20rem;
    }
  }
}

@keyframes flex-card-wave {
  0%,
  8%,
  100% {
    transform: translateY(0);
  }
  3% {
    transform: translateY(-0.625rem);
  }
  5.5% {
    transform: translateY(0);
  }
}

@keyframes flex-card-number {
  from {
    opacity: 0;
    transform: translateY(-2.5rem) scale(0.9);
  }
}

@keyframes flex-card-nudge {
  50% {
    transform: translateX(0.3rem);
  }
}

@keyframes flex-card-ring {
  0% {
    box-shadow: 0 0 0 0 rgb(255 255 255 / 0.5);
  }
  70%,
  100% {
    box-shadow: 0 0 0 0.75rem rgb(255 255 255 / 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .flex-card,
  .flex-card__hint,
  .flex-card__chevron,
  .flex-card__rise,
  .flex-card__number,
  .flex-card__art {
    animation: none !important;
  }
}
</style>
