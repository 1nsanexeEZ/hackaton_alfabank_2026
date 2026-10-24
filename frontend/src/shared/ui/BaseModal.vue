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

/**
 * Модальное окно: закрывается по Esc и клику по фону, фокус уходит внутрь окна.
 * Пока окно открыто, у <html> класс `has-modal`: анимации страницы под затемнением встают на паузу
 * (правило в app/styles), иначе их перерисовка мешает плавно прокручивать окно.
 */
withDefaults(defineProps<{ title: string; description?: string; wide?: boolean }>(), {
  description: undefined,
  wide: false,
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
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-from-class="opacity-0"
      enter-active-class="transition duration-150"
      leave-to-class="opacity-0"
      leave-active-class="transition duration-100"
    >
      <div
        v-if="open"
        class="fixed inset-0 z-[100] flex items-end justify-center bg-night/50 p-0 sm:items-center sm:p-6"
        @click.self="close"
      >
        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`${id}-title`"
          :class="[
            'modal__panel flex max-h-[92dvh] w-full flex-col rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl',
            wide ? 'sm:max-w-3xl' : 'sm:max-w-lg',
          ]"
        >
          <header class="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
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
          <div class="overflow-y-auto overscroll-contain px-5 py-5 sm:px-6">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-4 sm:px-6">
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
