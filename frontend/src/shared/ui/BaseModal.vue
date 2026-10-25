<script lang="ts">
/**
 * Сколько окон держат страницу сейчас — общее на все экземпляры. Из одного окна часто открывают
 * другое («Мои заявки» → карточка): закрытие первого не должно снимать блокировку со второго.
 */
let lockedBy = 0
</script>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

import {
  afterThisFlush,
  isSheet,
  isSwapIn,
  isSwapOut,
  markModalEnter,
  markModalLeave,
  prefersReducedMotion,
} from './modalMotion'

/**
 * Модальное окно: закрывается по Esc и клику по фону, фокус уходит внутрь окна.
 * Пока окно открыто, у <html> класс `has-modal`: анимации страницы под затемнением встают на паузу
 * (правило в app/styles), иначе их перерисовка мешает плавно прокручивать окно.
 * `bare` — окно без своей шапки, прокрутки и подвала: их рисует содержимое (карточка заявки).
 * Слот получает `close` и `titleId` — id заголовка, на который ссылается aria-labelledby окна.
 *
 * Появление и уход анимированы (modalMotion): затемнение проявляется, окно поднимается с лёгким
 * масштабом, на телефоне выезжает шторкой снизу. Если одно окно сменяет другое в тот же кадр —
 * затемнение одно и не моргает, старое окно уходит влево, новое приходит справа.
 */
withDefaults(defineProps<{ title: string; description?: string; wide?: boolean; bare?: boolean }>(), {
  description: undefined,
  wide: false,
  bare: false,
})

const open = defineModel<boolean>('open', { required: true })

const id = useId()
const panel = ref<HTMLElement>()
let returnFocusTo: HTMLElement | null = null

function close() {
  open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

let locking = false

function lockPage(locked: boolean) {
  if (locked === locking) return
  locking = locked
  lockedBy += locked ? 1 : -1
  const anyOpen = lockedBy > 0
  document.body.style.overflow = anyOpen ? 'hidden' : ''
  document.documentElement.classList.toggle('has-modal', anyOpen)
}

watch(open, async (isOpen) => {
  if (isOpen) {
    returnFocusTo = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', onKeydown)
    lockPage(true)
    await nextTick()
    panel.value?.querySelector<HTMLElement>('input, select, textarea, button:not([data-close])')?.focus()
  } else {
    document.removeEventListener('keydown', onKeydown)
    lockPage(false)
    returnFocusTo?.focus()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  lockPage(false)
})

// --- Анимация: Web Animations, чтобы решить «переход или нет» уже после всех хуков этого кадра ---

const EASE_OUT = 'cubic-bezier(0.22, 1, 0.36, 1)'
const EASE_IN = 'cubic-bezier(0.4, 0, 1, 1)'

const parts = (el: Element) => ({
  backdrop: el.querySelector<HTMLElement>('.modal__backdrop'),
  panel: el.querySelector<HTMLElement>('.modal__panel'),
})

function onBeforeEnter(el: Element) {
  markModalEnter()
  // До первого кадра окно невидимо: решение, как появиться, принимается микрозадачей позже
  ;(el as HTMLElement).style.opacity = '0'
}

async function onEnter(el: Element, done: () => void) {
  await afterThisFlush()
  const root = el as HTMLElement
  root.style.opacity = ''
  const { backdrop, panel } = parts(el)
  if (prefersReducedMotion()) {
    await root.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120 }).finished.catch(() => undefined)
    return done()
  }
  const swap = isSwapIn()
  const sheet = isSheet()
  const animations: Animation[] = []
  if (backdrop && !swap) animations.push(backdrop.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease-out' }))
  if (panel) {
    const from = swap
      ? { opacity: 0, transform: sheet ? 'translateY(1.5rem)' : 'translateX(2.5rem) scale(0.98)' }
      : { opacity: sheet ? 1 : 0, transform: sheet ? 'translateY(100%)' : 'translateY(1rem) scale(0.97)' }
    animations.push(
      panel.animate([from, { opacity: 1, transform: 'none' }], { duration: sheet && !swap ? 380 : 320, easing: EASE_OUT }),
    )
  }
  await Promise.all(animations.map((animation) => animation.finished.catch(() => undefined)))
  done()
}

function onBeforeLeave() {
  markModalLeave()
}

async function onLeave(el: Element, done: () => void) {
  await afterThisFlush()
  const { backdrop, panel } = parts(el)
  if (prefersReducedMotion()) {
    await (el as HTMLElement).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 100, fill: 'forwards' }).finished.catch(() => undefined)
    return done()
  }
  const swap = isSwapOut()
  const sheet = isSheet()
  const animations: Animation[] = []
  if (backdrop) {
    // При переходе под уходящим уже лежит затемнение нового окна — своё гасим сразу, иначе вдвое темнее
    animations.push(
      backdrop.animate([{ opacity: 1 }, { opacity: 0 }], swap ? { duration: 0, fill: 'forwards' } : { duration: 200, delay: 40, easing: 'ease-in', fill: 'forwards' }),
    )
  }
  if (panel) {
    const to = swap
      ? { opacity: 0, transform: sheet ? 'translateY(1rem)' : 'translateX(-2.5rem) scale(0.98)' }
      : { opacity: sheet ? 1 : 0, transform: sheet ? 'translateY(100%)' : 'translateY(0.75rem) scale(0.97)' }
    animations.push(
      panel.animate([{ opacity: 1, transform: 'none' }, to], { duration: sheet && !swap ? 280 : 200, easing: EASE_IN, fill: 'forwards' }),
    )
  }
  await Promise.all(animations.map((animation) => animation.finished.catch(() => undefined)))
  done()
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @before-enter="onBeforeEnter" @enter="onEnter" @before-leave="onBeforeLeave" @leave="onLeave">
      <div v-if="open" class="fixed inset-0 z-[100] flex items-end justify-center p-0 sm:items-center sm:p-6">
        <div class="modal__backdrop absolute inset-0 bg-night/50" aria-hidden="true" @click="close" />
        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`${id}-title`"
          :class="[
            'modal__panel relative flex max-h-[92dvh] w-full flex-col rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl',
            wide ? 'sm:max-w-3xl' : 'sm:max-w-lg',
            // Тонкая светлая обводка: край окна с тёмной шапкой виден и на тёмной странице
            bare && 'overflow-hidden ring-1 ring-white/10',
          ]"
        >
          <slot v-if="bare" v-bind="{ close, titleId: `${id}-title` }" />
          <header v-else class="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
            <div>
              <h2 :id="`${id}-title`" class="text-lg font-bold text-ink">{{ title }}</h2>
              <p v-if="description" class="mt-1 text-sm text-ink-secondary">{{ description }}</p>
            </div>
            <button
              type="button"
              data-close
              class="-mr-2 flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-surface hover:text-ink"
              aria-label="Закрыть"
              @click="close"
            >
              <X class="size-5" aria-hidden="true" />
            </button>
          </header>
          <div v-if="!bare" class="overflow-y-auto overscroll-contain px-5 py-5 sm:px-6">
            <slot v-bind="{ close, titleId: `${id}-title` }" />
          </div>
          <footer v-if="!bare && $slots.footer" class="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-4 sm:px-6">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Окно перерисовывается и раскладывается само по себе: изменения внутри не трогают страницу под ним */
.modal__panel {
  contain: layout paint;
  isolation: isolate;
}
</style>
