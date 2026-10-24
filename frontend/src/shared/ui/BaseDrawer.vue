<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

/**
 * Панель, которая выезжает справа поверх страницы. Страница под ней размывается, в слот
 * `backdrop` кладётся декоративный слой для открытой части экрана. Закрывается по Esc, крестику
 * и клику по фону; фокус уходит внутрь панели, не выходит из неё по Tab и возвращается после закрытия.
 * На телефоне панель во всю ширину и начинается ниже полосы фона, на остальных экранах — справа на всю высоту.
 * Закрытие тоже анимировано: перед уходом область фона получает атрибут `data-leaving`, и декор в слоте
 * уходит вместе с панелью. Атрибут, а не пропс: компоненты внутри уходящей панели Vue уже не перерисовывает.
 */
withDefaults(defineProps<{ title: string; description?: string; eyebrow?: string }>(), {
  description: undefined,
  eyebrow: undefined,
})

const open = defineModel<boolean>('open', { required: true })

const id = useId()
const panel = ref<HTMLElement>()
let returnFocusTo: HTMLElement | null = null

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function close() {
  open.value = false
}

function markLeaving(el: Element) {
  el.querySelector('.drawer__decor')?.setAttribute('data-leaving', '')
}

function keepFocusInside(event: KeyboardEvent) {
  const items = panel.value ? [...panel.value.querySelectorAll<HTMLElement>(FOCUSABLE)] : []
  const first = items[0]
  const last = items[items.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
  else if (event.key === 'Tab') keepFocusInside(event)
}

watch(open, async (isOpen) => {
  if (isOpen) {
    returnFocusTo = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', onKeydown)
    document.body.style.overflow = 'hidden'
    await nextTick()
    panel.value?.querySelector<HTMLElement>('input, select, textarea, button:not([data-close])')?.focus()
  } else {
    document.removeEventListener('keydown', onKeydown)
    document.body.style.overflow = ''
    returnFocusTo?.focus()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <!-- Длительность — по самым долгим вложенным переходам: фон, панель и декор двигаются сами -->
    <Transition name="drawer" :duration="{ enter: 520, leave: 560 }" @before-leave="markLeaving">
      <div v-if="open" class="drawer fixed inset-0 z-[100]">
        <div class="drawer__backdrop absolute inset-0" aria-hidden="true" @click="close" />
        <div class="drawer__decor pointer-events-none absolute">
          <slot name="backdrop" />
        </div>
        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`${id}-title`"
          :aria-describedby="description ? `${id}-description` : undefined"
          class="drawer__panel absolute flex flex-col gap-6 overflow-y-auto bg-white px-5 pt-5 pb-8 text-ink shadow-2xl sm:px-11 sm:pt-8"
        >
          <div class="flex items-center justify-between gap-4">
            <span v-if="eyebrow" class="text-xs font-semibold tracking-wider text-brand uppercase">{{ eyebrow }}</span>
            <button
              type="button"
              data-close
              class="ml-auto flex size-11 shrink-0 items-center justify-center rounded-2xl bg-surface text-ink-secondary transition-colors hover:bg-surface-strong hover:text-ink"
              aria-label="Закрыть"
              @click="close"
            >
              <X class="size-5" aria-hidden="true" />
            </button>
          </div>
          <div>
            <h2 :id="`${id}-title`" class="text-2xl font-bold tracking-tight text-ink sm:text-[1.875rem] sm:leading-tight">
              {{ title }}
            </h2>
            <p v-if="description" :id="`${id}-description`" class="mt-1.5 text-sm text-ink-secondary sm:text-[0.9375rem]">
              {{ description }}
            </p>
          </div>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer__backdrop {
  background: rgb(18 18 19 / 0.55);
  backdrop-filter: blur(16px) saturate(120%);
  cursor: pointer;
}

@supports not (backdrop-filter: blur(1px)) {
  .drawer__backdrop {
    background: rgb(18 18 19 / 0.85);
  }
}

/* Телефон: полоса фона сверху, панель под ней во всю ширину */
.drawer__decor {
  top: 0;
  left: 0;
  right: 0;
  height: 13rem;
}

.drawer__panel {
  top: 12rem;
  right: 0;
  bottom: 0;
  left: 0;
  border-radius: 2rem 2rem 0 0;
}

/* Шире телефона: панель справа на всю высоту, фон — вся остальная часть экрана */
@media (width >= 40rem) {
  .drawer__decor {
    bottom: 0;
    right: min(30rem, 100%);
    height: auto;
  }

  .drawer__panel {
    top: 0;
    left: auto;
    width: min(30rem, 100%);
    border-radius: 2rem 0 0 2rem;
  }
}

.drawer-enter-active .drawer__backdrop {
  transition: opacity 340ms ease-out;
}

/* Закрытие в обратном порядке: буквы улетают, панель уезжает, размытие гаснет последним */
.drawer-leave-active .drawer__backdrop {
  transition: opacity 420ms ease-in 120ms;
}

.drawer-enter-from .drawer__backdrop,
.drawer-leave-to .drawer__backdrop {
  opacity: 0;
}

.drawer-enter-active .drawer__panel {
  transition: transform 480ms cubic-bezier(0.22, 1, 0.36, 1);
}

.drawer-leave-active .drawer__panel {
  transition: transform 360ms cubic-bezier(0.4, 0, 0.2, 1) 60ms;
}

.drawer-enter-from .drawer__panel,
.drawer-leave-to .drawer__panel {
  transform: translateX(100%);
}
</style>
