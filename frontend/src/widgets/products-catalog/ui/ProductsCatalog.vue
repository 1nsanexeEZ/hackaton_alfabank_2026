<script setup lang="ts">
import { Calculator, ChevronLeft, ChevronRight, Zap } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { ProductFlexCard, type ProductCatalog } from '@/entities/credit-product'
import { ProductFilterControl, useProductFilter } from '@/features/filter-products'
import { SECTION_ID } from '@/shared/config'
import { BaseButton, BaseContainer, DecorSticker, PeekSticker, SectionHeader } from '@/shared/ui'

const props = defineProps<{ products: ProductCatalog }>()

const emit = defineEmits<{
  /** Рассчитать платёж по продукту */
  calculate: [productId: string]
  /** Сразу перейти к заявке */
  apply: [productId: string]
}>()

/** Сколько раскрытая карточка ждёт, прежде чем ряд переключится сам */
const AUTOPLAY_MS = 6000

const { filter, filteredProducts } = useProductFilter(() => props.products)

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
 * Автопрокрутка только на десктопе, где карточки стоят в ряд: на телефоне они в столбик,
 * и само раскрытие сдвигало бы страницу. Без анимации по настройкам системы — тоже нет.
 */
const row = ref<HTMLElement>()
const isDesktop = ref(false)
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
  <section :id="SECTION_ID.products" class="py-16 lg:py-24">
    <BaseContainer class="relative">
      <DecorSticker
        class="absolute -top-12 right-24"
        :icon="Zap"
        title="Решение онлайн"
        caption="без похода в банк"
        :tilt="6"
        :delay="1"
      />
      <SectionHeader
        title="Кредиты для бизнеса"
        description="Условия демонстрационные: итоговые ставка и лимит зависят от решения банка по заявке."
      >
        <template #aside>
          <ProductFilterControl v-model="filter" class="self-start lg:self-auto" />
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
        class="relative isolate mt-8 flex flex-col gap-3 lg:mt-5 lg:h-[28rem] lg:flex-row lg:gap-4"
        @mouseenter="isHovered = true"
        @mouseleave="isHovered = false"
        @focusin="hasFocusInside = true"
        @focusout="onFocusOut"
      >
        <PeekSticker art="rocket" from="right" class="absolute top-28 -right-20 -z-10" :tilt="62" :delay="1" />
        <ProductFlexCard
          v-for="(product, index) in filteredProducts"
          :key="product.id"
          :product="product"
          :index="index"
          :expanded="product.id === expandedId"
          :autoplay-ms="autoplayMs"
          :paused="paused"
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

      <!-- Индикаторы как в сторис: активный длиннее и заполняется вместе с полосой в карточке -->
      <div class="mt-6 hidden items-center gap-2 lg:flex">
        <button
          v-for="product in filteredProducts"
          :key="product.id"
          type="button"
          class="catalog-seg relative h-1.5 overflow-hidden rounded-full bg-surface-strong"
          :class="product.id === expandedId ? 'w-16' : 'w-7'"
          :aria-label="`Показать продукт «${product.title}»`"
          :aria-current="product.id === expandedId || undefined"
          @click="expandedId = product.id"
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
    </BaseContainer>
  </section>
</template>

<style scoped>
.catalog-arrow {
  transition:
    background-color 0.2s,
    scale 0.2s;
}

.catalog-arrow:hover {
  background-color: var(--color-surface-strong);
  scale: 1.06;
}

.catalog-seg {
  transition: width 0.5s cubic-bezier(0.22, 1, 0.36, 1);
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
  .catalog-dot {
    animation: none;
  }
}
</style>
