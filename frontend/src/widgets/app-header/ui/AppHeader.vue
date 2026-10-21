<script setup lang="ts">
import { LogIn, Menu, X } from 'lucide-vue-next'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { LANDING_NAV, ROUTE_PATH, SECTION_ID, sectionHref } from '@/shared/config'
import { AppLogo, BaseButton, BaseContainer } from '@/shared/ui'

const isMenuOpen = ref(false)
const route = useRoute()

function closeMenu() {
  isMenuOpen.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeMenu()
}

// На десктопе мобильное меню не нужно: закрываем его, если окно расширили
const desktopQuery = typeof window !== 'undefined' ? window.matchMedia('(min-width: 64rem)') : null

function onDesktopChange(event: MediaQueryListEvent) {
  if (event.matches) closeMenu()
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  desktopQuery?.addEventListener('change', onDesktopChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  desktopQuery?.removeEventListener('change', onDesktopChange)
})

watch(() => route.fullPath, closeMenu)
</script>

<template>
  <header class="sticky top-0 z-50 bg-night text-on-night">
    <BaseContainer class="flex h-16 items-center justify-between gap-6 lg:h-18">
      <RouterLink :to="ROUTE_PATH.home" class="shrink-0 rounded-lg" aria-label="Кредитный кабинет — на главную">
        <AppLogo inverted />
      </RouterLink>

      <nav class="hidden lg:block" aria-label="Разделы">
        <ul class="flex items-center gap-6 xl:gap-8">
          <li v-for="link in LANDING_NAV" :key="link.section">
            <a
              :href="sectionHref(link.section)"
              class="text-[15px] font-medium whitespace-nowrap text-on-night-secondary transition-colors hover:text-on-night"
            >
              {{ link.label }}
            </a>
          </li>
        </ul>
      </nav>

      <div class="flex items-center gap-2">
        <!-- max-*:hidden, а не hidden sm:inline-flex: у BaseButton свой display, обычный hidden его не перебьёт -->
        <BaseButton variant="glass" size="s" :to="ROUTE_PATH.login" class="max-sm:hidden">
          <LogIn class="size-4" aria-hidden="true" />
          Войти
        </BaseButton>
        <BaseButton size="s" :href="sectionHref(SECTION_ID.application)" class="max-md:hidden">
          Оформить заявку
        </BaseButton>
        <button
          type="button"
          class="-mr-2 flex size-10 items-center justify-center rounded-lg text-on-night transition-colors hover:bg-night-glass lg:hidden"
          :aria-expanded="isMenuOpen"
          aria-controls="mobile-menu"
          :aria-label="isMenuOpen ? 'Закрыть меню' : 'Открыть меню'"
          @click="isMenuOpen = !isMenuOpen"
        >
          <X v-if="isMenuOpen" class="size-6" aria-hidden="true" />
          <Menu v-else class="size-6" aria-hidden="true" />
        </button>
      </div>
    </BaseContainer>

    <Transition
      enter-from-class="opacity-0 -translate-y-2"
      enter-active-class="transition duration-200"
      leave-to-class="opacity-0 -translate-y-2"
      leave-active-class="transition duration-150"
    >
      <div v-if="isMenuOpen" id="mobile-menu" class="border-t border-night-line lg:hidden">
        <BaseContainer class="pt-2 pb-6">
          <nav aria-label="Разделы">
            <ul>
              <li v-for="link in LANDING_NAV" :key="link.section">
                <a
                  :href="sectionHref(link.section)"
                  class="block border-b border-night-line py-4 text-lg font-medium text-on-night"
                  @click="closeMenu"
                >
                  {{ link.label }}
                </a>
              </li>
            </ul>
          </nav>
          <div class="mt-6 grid gap-3 sm:grid-cols-2">
            <BaseButton variant="glass" :to="ROUTE_PATH.login" block>
              <LogIn class="size-4" aria-hidden="true" />
              Войти в кабинет
            </BaseButton>
            <BaseButton :href="sectionHref(SECTION_ID.application)" block @click="closeMenu">
              Оформить заявку
            </BaseButton>
          </div>
        </BaseContainer>
      </div>
    </Transition>
  </header>
</template>
