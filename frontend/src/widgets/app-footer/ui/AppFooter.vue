<script setup lang="ts">
import { useProductCatalog } from '@/entities/credit-product'
import { LANDING_NAV, SECTION_ID, sectionHref } from '@/shared/config'
import { AppLogo, BaseContainer } from '@/shared/ui'

const { products } = useProductCatalog()

const currentYear = new Date().getFullYear()
</script>

<template>
  <footer class="bg-night text-on-night">
    <BaseContainer class="py-12 lg:py-16">
      <div class="grid gap-10 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr]">
        <div class="max-w-sm">
          <AppLogo inverted />
          <p class="mt-4 text-sm text-on-night-secondary">
            Цифровой кредитный конвейер для малого и микробизнеса: от выбора продукта до решения по заявке.
          </p>
        </div>

        <nav aria-label="Продукты">
          <p class="text-sm font-semibold">Продукты</p>
          <ul class="mt-4 space-y-3">
            <li v-for="product in products ?? []" :key="product.id">
              <a
                :href="sectionHref(SECTION_ID.products)"
                class="text-sm text-on-night-secondary transition-colors hover:text-on-night"
              >
                {{ product.title }}
              </a>
            </li>
          </ul>
        </nav>

        <nav aria-label="Разделы сайта">
          <p class="text-sm font-semibold">Разделы</p>
          <ul class="mt-4 space-y-3">
            <li v-for="link in LANDING_NAV" :key="link.section">
              <a
                :href="sectionHref(link.section)"
                class="text-sm text-on-night-secondary transition-colors hover:text-on-night"
              >
                {{ link.label }}
              </a>
            </li>
          </ul>
        </nav>
      </div>

      <div
        class="mt-12 flex flex-col gap-3 border-t border-night-line pt-6 text-xs text-on-night-secondary lg:flex-row lg:justify-between"
      >
        <p>© {{ currentYear }} Команда хакатона «Альфа Будущее»</p>
        <p class="max-w-2xl lg:text-right">
          Прототип. Условия, компании и заявки синтетические и не являются публичной офертой.
        </p>
      </div>
    </BaseContainer>
  </footer>
</template>
