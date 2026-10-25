<script setup lang="ts">
import { Calculator, ChevronLeft, ChevronRight, Zap } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { ProductFlexCard, type ProductCatalog } from '@/entities/credit-product'
import { ProductFilterControl, PurposeFilterControl, useProductFilter } from '@/features/filter-products'
import { SECTION_ID } from '@/shared/config'
import { BaseButton, BaseContainer, HintCard, SectionHeader } from '@/shared/ui'

import { useCardWindow } from '../model/useCardWindow'

const props = defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{
  /** Рассчитать платёж по продукту */
  calculate: [productId: string]
  /** Сразу перейти к заявке */
  apply: [productId: string]
}>()

/** Сколько раскрытая карточка ждёт, прежде чем ряд переключится сам */
const AUTOPLAY_MS = 6000

const { filter, purpose, purposeError, filteredProducts } = useProductFilter(() => props.products)

// В ряду всегда раскрыта одна карточка
const expandedId = ref(props.products[0].id)

watch(filteredProducts, (list) => {
  const first = list[0]
  if (first && !list.some((product) => product.id === expandedId.value)) expandedId.value = first.id
})

const activeIndex = computed(() => filteredProducts.value.findIndex((product) => product.id === expandedId.value))

function go(offset: number) {
  const list = filteredProducts.value
  if (!list.length) return
  const next = list[(activeIndex.value + offset + list.length) % list.length]
  if (next) expandedId.value = next.id
}

/*
 * Десктоп: ряд — окно. Раскрытая карточка не уже 30rem, рядом столько полосок, сколько влезает,
 * остальные за краем; окно едет за раскрытой (стрелки, автопрокрутка, индикатор).
 * Телефон и планшет: лента полных карточек, листается свайпом, индикатор следит за прокруткой.
 */
const viewport = ref<HTMLElement>()
const track = ref<HTMLElement>()
const { offset, expandedWidth, inWindow, hasBefore, hasAfter } = useCardWindow(
  viewport,
  () => filteredProducts.value.length,
  () => activeIndex.value,
)

const trackStyle = computed(() =>
  isDesktop.value
    ? { transform: `translateX(-${offset.value}px)`, '--catalog-expanded-w': `${expandedWidth.value}px` }
    : undefined,
)

const pad = (value: number) => String(value).padStart(2, '0')

function scrollToCard(index: number, behavior: ScrollBehavior) {
  const card = track.value?.children[index] as HTMLElement | undefined
  viewport.value?.scrollTo({ left: card ? card.offsetLeft - (track.value?.offsetLeft ?? 0) : 0, behavior })
}

/** Индикатор: на десктопе раскрывает продукт, на телефоне листает ленту к нему */
function show(index: number) {
  const product = filteredProducts.value[index]
  if (!product) return
  if (isDesktop.value) expandedId.value = product.id
  else scrollToCard(index, 'smooth')
}

// На телефоне «текущая» карточка — та, что ближе всех к левому краю ленты
function onScroll() {
  if (isDesktop.value) return
  const cards = [...(track.value?.children ?? [])] as HTMLElement[]
  const left = (viewport.value?.scrollLeft ?? 0) + (track.value?.offsetLeft ?? 0)
  let nearest = 0
  cards.forEach((card, index) => {
    if (Math.abs(card.offsetLeft - left) < Math.abs((cards[nearest]?.offsetLeft ?? 0) - left)) nearest = index
  })
  const product = filteredProducts.value[nearest]
  if (product) expandedId.value = product.id
}

// Сменили фильтр: лента остаётся на текущем продукте, а если его в списке нет — на первом
watch(filteredProducts, () => !isDesktop.value && scrollToCard(Math.max(activeIndex.value, 0), 'instant'), {
  flush: 'post',
})

/*
 * Автопрокрутка только на десктопе, где карточки стоят в ряд: на телефоне они в столбик,
 * и само раскрытие сдвигало бы страницу. Без анимации по настройкам системы — тоже нет.
 */
const row = ref<HTMLElement>()
// Сразу, а не в onMounted: иначе на десктопе первый кадр рисуется лентой и карточки схлопываются на глазах
const isDesktop = ref(typeof window !== 'undefined' && window.matchMedia('(min-width: 64rem)').matches)
const reducedMotion = ref(false)
const isHovered = ref(false)
const hasFocusInside = ref(false)
const isVisible = ref(false)

const autoplayMs = computed(() => (isDesktop.value && !reducedMotion.value && filteredProducts.value.length > 1 ? AUTOPLAY_MS : 0))
const paused = computed(() => isHovered.value || hasFocusInside.value || !isVisible.value)

let desktopQuery: MediaQueryList | undefined
let motionQuery: MediaQueryList | undefined
let observer: IntersectionObserver | undefined

const syncDesktop = () => (isDesktop.value = desktopQuery?.matches ?? false)
const syncMotion = () => (reducedMotion.value = motionQuery?.matches ?? false)

onMounted(() => {
  desktopQuery = window.matchMedia('(min-width: 64rem)')
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  syncDesktop()
  syncMotion()
  desktopQuery.addEventListener('change', syncDesktop)
  motionQuery.addEventListener('change', syncMotion)

  if (!('IntersectionObserver' in window)) {
    isVisible.value = true
    return
  }
  // Вне экрана полоса и волна стоят: пользователь не должен вернуться к «уехавшей» карточке
  observer = new IntersectionObserver(([entry]) => (isVisible.value = entry?.isIntersecting ?? false), {
    threshold: 0.4,
  })
  if (row.value) observer.observe(row.value)
})

onBeforeUnmount(() => {
  desktopQuery?.removeEventListener('change', syncDesktop)
  motionQuery?.removeEventListener('change', syncMotion)
  observer?.disconnect()
})

function onFocusOut(event: FocusEvent) {
  hasFocusInside.value = row.value?.contains(event.relatedTarget as Node | null) ?? false
}
</script>

<template>
  <!-- overflow-x-clip: лента карточек и тень подсказки у края окна не расширяют страницу -->
  <section :id="SECTION_ID.products" class="overflow-x-clip py-16 lg:py-24">
    <BaseContainer class="relative">
      <HintCard
        class="absolute -top-12 right-24"
        :icon="Zap"
        title="Решение онлайн"
        caption="без похода в банк"
        :delay="1"
      />
      <SectionHeader
        title="Кредиты для бизнеса"
        description="Условия демонстрационные: итоговые ставка и лимит зависят от решения банка по заявке."
      >
        <template #aside>
          <!-- shrink-0: на 1024 px длинное описание иначе сжимает фильтр и обрезает «Деньги частями» -->
          <div class="flex flex-col gap-2 self-start sm:flex-row sm:items-center lg:shrink-0 lg:self-auto">
            <ProductFilterControl v-model="filter" />
            <PurposeFilterControl v-model="purpose" class="sm:w-64" />
          </div>
          <p v-if="purposeError" class="mt-1 text-xs text-ink-secondary">Не удалось подобрать по цели — показаны все продукты</p>
        </template>
      </SectionHeader>

      <div class="mt-8 hidden items-center justify-between gap-6 lg:mt-12 lg:flex">
        <p class="flex items-center gap-2.5 text-sm text-ink-secondary">
          <span class="catalog-dot size-2 rounded-full bg-brand" aria-hidden="true" />
          Наведите на карточку или нажмите — она раскроется
        </p>
        <div class="flex gap-2">
          <button
            type="button"
            class="catalog-arrow flex size-12 items-center justify-center rounded-full bg-surface text-ink"
            aria-label="Предыдущий продукт"
            @click="go(-1)"
          >
            <ChevronLeft class="size-5" :stroke-width="2.4" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="catalog-arrow flex size-12 items-center justify-center rounded-full bg-surface text-ink"
            aria-label="Следующий продукт"
            @click="go(1)"
          >
            <ChevronRight class="size-5" :stroke-width="2.4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div
        ref="row"
        class="relative isolate mt-8 lg:mt-5"
        @mouseenter="isHovered = true"
        @mouseleave="isHovered = false"
        @focusin="hasFocusInside = true"
        @focusout="onFocusOut"
      >
        <!-- Телефон: лента с прокруткой до краёв экрана. Десктоп: окно, лишнее обрезано по бокам, но не сверху — карточки подпрыгивают -->
        <div
          ref="viewport"
          class="catalog-viewport relative -mx-4 snap-x snap-mandatory scroll-px-4 overflow-x-auto px-4 sm:-mx-6 sm:scroll-px-6 sm:px-6 lg:mx-0 lg:snap-none lg:overflow-x-clip lg:px-0"
          @scroll.passive="onScroll"
        >
          <div ref="track" class="catalog-track flex w-max gap-3 lg:h-[28rem] lg:gap-4" :style="trackStyle">
            <ProductFlexCard
              v-for="(product, index) in filteredProducts"
              :key="product.id"
              :product="product"
              :index="index"
              :expanded="!isDesktop || product.id === expandedId"
              :autoplay-ms="autoplayMs"
              :paused="paused"
              :inert="(isDesktop && !inWindow(index)) || undefined"
              class="w-[82vw] shrink-0 snap-start sm:w-[56vw] lg:w-auto"
              @expand="expandedId = product.id"
              @finished="go(1)"
            >
              <template #actions>
                <BaseButton variant="inverted" @click="emit('apply', product.id)">Оформить</BaseButton>
                <BaseButton variant="glass" @click="emit('calculate', product.id)">
                  <Calculator class="size-4" aria-hidden="true" />
                  Рассчитать платёж
                </BaseButton>
              </template>
            </ProductFlexCard>
          </div>
          <!-- Затухание с той стороны, где за краем есть ещё продукты -->
          <span v-if="isDesktop && hasBefore" class="catalog-fade catalog-fade--start" aria-hidden="true" />
          <span v-if="isDesktop && hasAfter" class="catalog-fade catalog-fade--end" aria-hidden="true" />
        </div>
      </div>

      <!-- Индикаторы как в сторис: номер из скольких и сегменты, которые сжимаются под любое число продуктов -->
      <div class="mt-6 flex items-center gap-4">
        <p class="shrink-0 text-sm font-semibold text-ink tabular-nums" aria-live="polite">
          {{ pad(activeIndex + 1) }}
          <span class="font-medium text-ink-muted">/ {{ pad(filteredProducts.length) }}</span>
        </p>
        <div class="flex max-w-md flex-1 items-center gap-1.5">
          <button
            v-for="(product, index) in filteredProducts"
            :key="product.id"
            type="button"
            class="catalog-seg relative h-1.5 min-w-1 flex-1 overflow-hidden rounded-full bg-surface-strong"
            :class="product.id === expandedId && 'is-active'"
            :aria-label="`Показать продукт «${product.title}»`"
            :aria-current="product.id === expandedId || undefined"
            @click="show(index)"
          >
            <span
              v-if="product.id === expandedId"
              :key="expandedId"
              class="catalog-seg__fill absolute inset-0 rounded-full bg-brand"
              :class="{ 'is-static': !autoplayMs, 'is-paused': paused }"
              :style="{ animationDuration: `${autoplayMs}ms` }"
            />
          </button>
        </div>
      </div>
    </BaseContainer>
  </section>
</template>

<style scoped>
/* Стрелки: от них расходится кольцо, при наведении — увеличение с поворотом */
.catalog-arrow {
  transition:
    background-color 0.2s,
    scale 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
    rotate 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  animation: catalog-ring 2.4s ease-out infinite;
}

.catalog-arrow + .catalog-arrow {
  animation-delay: 1.2s;
}

.catalog-arrow:hover {
  animation: none;
  background-color: var(--color-surface-strong);
  scale: 1.1;
  rotate: -6deg;
}

.catalog-arrow:active {
  scale: 0.92;
}

@keyframes catalog-ring {
  0% {
    box-shadow: 0 0 0 0 rgb(18 18 19 / 0.22);
  }
  70%,
  100% {
    box-shadow: 0 0 0 0.75rem rgb(18 18 19 / 0);
  }
}

.catalog-seg {
  transition: flex-grow 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}

.catalog-seg.is-active {
  flex-grow: 4;
}

/* Лента на телефоне листается без полосы прокрутки */
.catalog-viewport {
  scrollbar-width: none;
}

.catalog-viewport::-webkit-scrollbar {
  display: none;
}

/* Выше и ниже ленты: накрывает и полоску, поднятую при наведении на 0.5rem, и её тень снизу */
.catalog-fade {
  position: absolute;
  top: -0.75rem;
  bottom: -3.75rem;
  z-index: 1;
  width: 4rem;
  pointer-events: none;
}

.catalog-fade--start {
  left: 0;
  background: linear-gradient(to right, var(--color-white, #fff), transparent);
}

.catalog-fade--end {
  right: 0;
  background: linear-gradient(to left, var(--color-white, #fff), transparent);
}

@media (width >= 64rem) {
  .catalog-track {
    transition: transform 0.6s cubic-bezier(0.05, 0.61, 0.41, 0.95);
  }
}

.catalog-seg__fill {
  transform-origin: left;
  animation: catalog-seg-fill linear both;
}

/* Без автопрокрутки индикатор просто закрашен */
.catalog-seg__fill.is-static {
  animation: none;
}

.catalog-seg__fill.is-paused {
  animation-play-state: paused;
}

@keyframes catalog-seg-fill {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}

.catalog-dot {
  animation: catalog-dot 1.4s ease-in-out infinite;
}

@keyframes catalog-dot {
  50% {
    transform: scale(1.6);
    opacity: 0.4;
  }
}

@media (prefers-reduced-motion: reduce) {
  .catalog-dot,
  .catalog-arrow {
    animation: none;
  }

  .catalog-track {
    transition: none;
  }
}
</style>

<style>
/*
 * Не scoped: ширину раскрытой карточки ряд передаёт через переменную. Наведение на полоску её
 * только приподнимает, поэтому ширины в ряду постоянны.
 */
@media (width >= 64rem) {
  .catalog-track > .flex-card.is-expanded {
    --flex-card-expanded-w: var(--catalog-expanded-w);
    --flex-card-expanded-grow: 0;
  }
}
</style>
