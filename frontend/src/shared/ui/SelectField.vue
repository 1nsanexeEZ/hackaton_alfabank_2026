<script setup lang="ts" generic="T extends string">
import { Check, ChevronDown } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    /** disabled — вариант виден, но выбрать его нельзя (например, занятый код) */
    options: readonly { value: T; label: string; disabled?: boolean }[]
    /** Компактная высота — для фильтров и форм админки */
    dense?: boolean
    /** Подпись только для скринридеров */
    hideLabel?: boolean
    /** Текст в поле, пока ничего не выбрано */
    placeholder?: string
  }>(),
  { dense: false, hideLabel: false, placeholder: undefined },
)

const model = defineModel<T>({ required: true })

/*
 * Свой выпадающий список вместо системного: тот рисуется браузером и выбивается из дизайна.
 * Список выносится в body и ставится по кнопке — так его не обрезает прокрутка модалки.
 * Клавиатура как у обычного select: стрелки, Home/End, Enter/пробел, Escape.
 */
const id = useId()
const listId = `${id}-list`

const trigger = ref<HTMLButtonElement>()
const list = ref<HTMLUListElement>()
const isOpen = ref(false)
const activeIndex = ref(-1)
const position = ref<Record<string, string>>({})
// Если снизу не хватает места — список открывается вверх
const opensUp = ref(false)

const LIST_GAP = 6
const LIST_MAX_HEIGHT = 288

const selected = computed(() => props.options.find((option) => option.value === model.value))
const selectedIndex = computed(() => props.options.findIndex((option) => option.value === model.value))

function place() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const spaceBelow = window.innerHeight - rect.bottom
  opensUp.value = spaceBelow < LIST_MAX_HEIGHT + LIST_GAP && rect.top > spaceBelow
  position.value = {
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    ...(opensUp.value
      ? { bottom: `${window.innerHeight - rect.top + LIST_GAP}px` }
      : { top: `${rect.bottom + LIST_GAP}px` }),
  }
}

const firstEnabled = () => props.options.findIndex((option) => !option.disabled)

function open() {
  place()
  activeIndex.value = selectedIndex.value >= 0 ? selectedIndex.value : Math.max(firstEnabled(), 0)
  isOpen.value = true
  nextTick(scrollToActive)
}

function close(returnFocus = false) {
  isOpen.value = false
  if (returnFocus) trigger.value?.focus()
}

function choose(index: number) {
  const option = props.options[index]
  if (option?.disabled) return
  if (option) model.value = option.value
  close(true)
}

function scrollToActive() {
  list.value?.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`)?.scrollIntoView({ block: 'nearest' })
}

/** Стрелками — к следующему доступному варианту, недоступные пропускаем */
function move(offset: number) {
  const count = props.options.length
  let next = activeIndex.value
  for (let step = 0; step < count; step++) {
    next = (next + offset + count) % count
    if (!props.options[next]?.disabled) break
  }
  activeIndex.value = next
  nextTick(scrollToActive)
}

function onKeydown(event: KeyboardEvent) {
  if (!isOpen.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
      event.preventDefault()
      open()
    }
    return
  }
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      move(1)
      break
    case 'ArrowUp':
      event.preventDefault()
      move(-1)
      break
    case 'Home':
      event.preventDefault()
      activeIndex.value = 0
      nextTick(scrollToActive)
      break
    case 'End':
      event.preventDefault()
      activeIndex.value = props.options.length - 1
      nextTick(scrollToActive)
      break
    case 'Enter':
    case ' ':
      event.preventDefault()
      choose(activeIndex.value)
      break
    case 'Escape':
      event.preventDefault()
      close(true)
      break
    case 'Tab':
      close()
      break
  }
}

function onPointerDownOutside(event: PointerEvent) {
  const target = event.target as Node
  if (!trigger.value?.contains(target) && !list.value?.contains(target)) close()
}

function unlisten() {
  document.removeEventListener('pointerdown', onPointerDownOutside)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
}

watch(isOpen, (value) => {
  if (!value) return unlisten()
  document.addEventListener('pointerdown', onPointerDownOutside)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
})

onBeforeUnmount(unlisten)
</script>

<template>
  <div>
    <span :id="`${id}-label`" class="mb-2 block text-sm font-medium text-ink" :class="hideLabel && 'sr-only'">
      {{ label }}
    </span>
    <button
      :id="id"
      ref="trigger"
      type="button"
      role="combobox"
      :aria-labelledby="`${id}-label ${id}`"
      :aria-expanded="isOpen"
      :aria-controls="listId"
      aria-haspopup="listbox"
      :aria-activedescendant="isOpen && activeIndex >= 0 ? `${id}-option-${activeIndex}` : undefined"
      :class="[
        'select-trigger relative flex w-full cursor-pointer items-center bg-surface pr-12 pl-4 text-left text-ink outline-none',
        'hover:bg-surface-strong focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-ink/20',
        dense ? 'h-11 rounded-lg text-sm' : 'h-14 rounded-xl text-base',
        isOpen && 'is-open bg-white ring-2 ring-brand/40 hover:bg-white',
      ]"
      @click="isOpen ? close() : open()"
      @keydown="onKeydown"
    >
      <span v-if="selected" class="truncate">{{ selected.label }}</span>
      <span v-else-if="placeholder" class="truncate text-ink-muted">{{ placeholder }}</span>
      <ChevronDown
        class="select-chevron pointer-events-none absolute top-1/2 right-4 size-5 -translate-y-1/2 text-ink-secondary"
        aria-hidden="true"
      />
    </button>

    <Teleport to="body">
      <Transition name="select-list">
        <ul
          v-if="isOpen"
          :id="listId"
          ref="list"
          role="listbox"
          :aria-labelledby="`${id}-label`"
          class="fixed z-[110] overflow-y-auto rounded-2xl bg-white p-1.5 shadow-[0_1.25rem_3rem_rgb(18_18_19/0.18),0_0_0_1px_var(--color-line)]"
          :class="opensUp ? 'origin-bottom' : 'origin-top'"
          :style="{ ...position, maxHeight: `${LIST_MAX_HEIGHT}px` }"
        >
          <li
            v-for="(option, index) in options"
            :id="`${id}-option-${index}`"
            :key="option.value"
            :data-index="index"
            role="option"
            :aria-selected="option.value === model"
            :aria-disabled="option.disabled || undefined"
            :class="[
              'select-option flex items-center justify-between gap-3 rounded-xl px-3.5',
              dense ? 'min-h-10 text-sm' : 'min-h-12 text-base',
              option.disabled ? 'cursor-default text-ink-muted' : option.value === model ? 'cursor-pointer font-medium text-brand' : 'cursor-pointer text-ink',
              index === activeIndex && !option.disabled && 'bg-surface',
            ]"
            :style="{ '--option-delay': `${index * 0.03}s` }"
            @pointermove="activeIndex = index"
            @click="choose(index)"
          >
            <span>{{ option.label }}</span>
            <Check v-if="option.value === model" class="size-4 shrink-0" :stroke-width="2.6" aria-hidden="true" />
          </li>
        </ul>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.select-trigger {
  transition:
    background-color 0.2s,
    box-shadow 0.2s;
}

.select-chevron {
  transition: rotate 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.is-open .select-chevron {
  rotate: 180deg;
}

.select-option {
  transition: background-color 0.15s;
}

/* Список раскрывается от кнопки, пункты появляются по очереди */
.select-list-enter-active {
  transition:
    opacity 0.2s,
    scale 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}

.select-list-leave-active {
  transition:
    opacity 0.15s,
    scale 0.15s;
}

.select-list-enter-from,
.select-list-leave-to {
  opacity: 0;
  scale: 0.96 0.9;
}

.select-list-enter-active .select-option {
  animation: select-option-in 0.3s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: var(--option-delay);
}

@keyframes select-option-in {
  from {
    opacity: 0;
    translate: 0 -0.375rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .select-list-enter-active,
  .select-list-leave-active,
  .select-chevron {
    transition: none;
  }

  .select-list-enter-active .select-option {
    animation: none;
  }
}
</style>
