<script setup lang="ts">
import { Bell, Building2, FileText, LogIn, LogOut, Menu, MessagesSquare, UserRound, X, type LucideIcon } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { assistant } from '@/entities/assistant'
import { customer, useCustomer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import { signOutWithTransition } from '@/features/customer-logout'
import { LANDING_NAV, ROUTE_PATH, sectionHref } from '@/shared/config'
import { AppLogo, BaseButton, BaseContainer } from '@/shared/ui'

import AssistantButton from './AssistantButton.vue'

/**
 * Кнопки «Оформить заявку» и «Войти» не решают сами, куда вести: страница или приложение
 * передают это в поток заявки, где проверяется вход.
 */
const emit = defineEmits<{ apply: []; login: []; open: [section: CabinetSection] }>()

/** Разделы кабинета клиента: модалки поверх сайта (widgets/apply-flow), профиль и поддержка — страницы */
type CabinetSection = 'applications' | 'notifications' | 'support' | 'company' | 'profile'

const CABINET_LINKS: readonly { section: CabinetSection; label: string; icon: LucideIcon }[] = [
  { section: 'applications', label: 'Мои заявки', icon: FileText },
  { section: 'notifications', label: 'Уведомления', icon: Bell },
  { section: 'support', label: 'Поддержка', icon: MessagesSquare },
  { section: 'company', label: 'Компания', icon: Building2 },
  { section: 'profile', label: 'Профиль', icon: UserRound },
]

const unread = computed(() => liveFeed.state.unread)

function openSection(section: CabinetSection) {
  closeMenu()
  emit('open', section)
}

const { isAuthenticated, name, logout } = useCustomer()

const isMenuOpen = ref(false)
const route = useRoute()

// Подтягиваем профиль по сохранённому токену, чтобы сразу показать, кто вошёл
onMounted(() => void customer.restore())

function closeMenu() {
  isMenuOpen.value = false
}

const router = useRouter()

/** Выход «чёрной дырой»: сессия стирается сразу, открывается главная */
function signOut() {
  closeMenu()
  signOutWithTransition({ logout, navigate: () => router.push(ROUTE_PATH.home) })
}

function apply() {
  closeMenu()
  emit('apply')
}

function login() {
  closeMenu()
  emit('login')
}

/**
 * Помощник доступен только вошедшему: гость по кнопке попадает на вход, как у «Оформить заявку».
 * Вошедшему без права assistant.use кнопку не показываем — бэкенд всё равно ответит 403.
 */
const canUseAssistant = computed(() => {
  const permissions = customer.state.me?.permissions ?? []
  return !isAuthenticated.value || permissions.includes('assistant.use') || permissions.includes('admin')
})

function toggleAssistant() {
  closeMenu()
  if (!isAuthenticated.value) emit('login')
  else assistant.toggle()
}

let stopStatusPolling = () => {}

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
  // Цвет точки на кнопке помощника — по GET /assistant/status, он открыт и гостю
  stopStatusPolling = assistant.startStatusPolling()
})

onBeforeUnmount(() => {
  stopStatusPolling()
  document.removeEventListener('keydown', onKeydown)
  desktopQuery?.removeEventListener('change', onDesktopChange)
})

watch(
  () => route.fullPath,
  () => closeMenu(),
)
</script>

<template>
  <header class="sticky top-0 z-50 bg-night text-on-night">
    <BaseContainer class="flex h-16 items-center justify-between gap-6 lg:h-18">
      <!-- data-brand-logo: сюда долетает «А» анимации входа, и логотип подсвечивается -->
      <RouterLink :to="ROUTE_PATH.home" class="shrink-0 rounded-lg" aria-label="Кредитный кабинет — на главную" data-brand-logo>
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
        <AssistantButton v-if="canUseAssistant" @click="toggleAssistant" />
        <!-- Колокольчик — уведомления, кнопка с именем — страница профиля; без выпадающего меню -->
        <template v-if="isAuthenticated">
          <button
            type="button"
            class="header-bell relative flex size-10 items-center justify-center rounded-lg bg-night-glass text-on-night transition-colors hover:bg-white/15 max-sm:hidden"
            :aria-label="unread ? `Уведомления, новых: ${unread}` : 'Уведомления'"
            @click="openSection('notifications')"
          >
            <Bell class="header-bell__icon size-[18px]" :class="{ 'has-unread': unread > 0 }" aria-hidden="true" />
            <span
              v-if="unread"
              class="absolute -top-1 -right-1 flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-brand px-1 text-[10px] leading-none font-bold text-white ring-2 ring-night"
              aria-hidden="true"
            >
              {{ unread > 99 ? '99+' : unread }}
            </span>
          </button>
          <button
            type="button"
            class="flex size-10 items-center justify-center rounded-lg bg-night-glass text-on-night transition-colors hover:bg-white/15 max-sm:hidden"
            aria-label="Поддержка"
            title="Поддержка"
            @click="openSection('support')"
          >
            <MessagesSquare class="size-[18px]" aria-hidden="true" />
          </button>
          <BaseButton variant="glass" size="s" class="max-sm:hidden" :aria-label="`Профиль: ${name}`" @click="openSection('profile')">
            <UserRound class="size-4 shrink-0" aria-hidden="true" />
            <span class="max-w-40 truncate max-xl:hidden">{{ name }}</span>
          </BaseButton>
        </template>
        <BaseButton v-else variant="glass" size="s" class="max-sm:hidden" @click="login">
          <LogIn class="size-4" aria-hidden="true" />
          Войти
        </BaseButton>
        <BaseButton size="s" class="max-md:hidden" @click="apply">Оформить заявку</BaseButton>
        <button
          type="button"
          class="relative -mr-2 flex size-10 items-center justify-center rounded-lg text-on-night transition-colors hover:bg-night-glass lg:hidden"
          :aria-expanded="isMenuOpen"
          aria-controls="mobile-menu"
          :aria-label="isMenuOpen ? 'Закрыть меню' : 'Открыть меню'"
          @click="isMenuOpen = !isMenuOpen"
        >
          <X v-if="isMenuOpen" class="size-6" aria-hidden="true" />
          <Menu v-else class="size-6" aria-hidden="true" />
          <span v-if="isAuthenticated && unread && !isMenuOpen" class="absolute top-2 right-1.5 size-2.5 rounded-full bg-brand ring-2 ring-night" aria-hidden="true" />
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
          <AssistantButton v-if="canUseAssistant" block class="mt-4" @click="toggleAssistant" />
          <ul v-if="isAuthenticated" class="mt-4 grid grid-cols-2 gap-2" aria-label="Кабинет">
            <li v-for="link in CABINET_LINKS" :key="link.section">
              <button
                type="button"
                class="flex w-full items-center gap-2.5 rounded-xl bg-night-glass px-3.5 py-3 text-left text-sm font-medium text-on-night"
                @click="openSection(link.section)"
              >
                <component :is="link.icon" class="size-4 shrink-0" aria-hidden="true" />
                <span class="flex-1">{{ link.label }}</span>
                <span v-if="link.section === 'notifications' && unread" class="rounded-full bg-brand px-1.5 py-0.5 text-[11px] leading-none font-bold text-white">
                  {{ unread }}
                </span>
              </button>
            </li>
          </ul>
          <div class="mt-6 grid gap-3 sm:grid-cols-2">
            <BaseButton v-if="isAuthenticated" variant="glass" block @click="signOut">
              <LogOut class="size-4" aria-hidden="true" />
              Выйти · {{ name }}
            </BaseButton>
            <BaseButton v-else variant="glass" block @click="login">
              <LogIn class="size-4" aria-hidden="true" />
              Войти в кабинет
            </BaseButton>
            <BaseButton block @click="apply">Оформить заявку</BaseButton>
          </div>
        </BaseContainer>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
/* Есть непрочитанные — колокольчик время от времени покачивается */
.header-bell__icon.has-unread {
  transform-origin: 50% 10%;
  animation: header-bell 4s ease-in-out infinite;
}

.header-bell:hover .header-bell__icon {
  animation: header-bell 0.8s ease-in-out;
}

@keyframes header-bell {
  0%,
  20%,
  100% {
    rotate: 0deg;
  }
  4%,
  12% {
    rotate: 14deg;
  }
  8%,
  16% {
    rotate: -12deg;
  }
}

@media (prefers-reduced-motion: reduce) {
  .header-bell__icon {
    animation: none !important;
  }
}
</style>
