<script setup lang="ts">
import { Check, ChevronDown, MessageSquare, Search } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

import { CLIENT_STATUS_META, CLOSED_CLIENT_STATUSES, toClientStatus } from '@/entities/application'
import { useProductCatalog } from '@/entities/credit-product'
import type { ApplicationStatusCode, AssistantApplicationDto, ClientStatus } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

/**
 * Выбор заявки, о которой спрашивают помощника: кнопка с выбранной заявкой и список по группам —
 * «В работе», «Завершённые» и «Без заявки». Стрелки, Enter и Esc работают; Esc закрывает только список.
 */
const props = defineProps<{ applications: readonly AssistantApplicationDto[]; selectedId: string | null }>()
const emit = defineEmits<{ select: [id: string | null] }>()

const id = useId()
const { products } = useProductCatalog()
const open = ref(false)
const query = ref('')
const active = ref(0)
const root = ref<HTMLElement>()
const search = ref<HTMLInputElement>()

const DOT_CLASS: Record<BadgeTone, string> = {
  neutral: 'bg-signal-off',
  brand: 'bg-brand',
  success: 'bg-signal-ok',
  warning: 'bg-signal-warn',
  info: 'bg-[#7ab3ff]',
  glass: 'bg-on-night-secondary',
}

interface Row {
  id: string | null
  title: string
  subtitle: string
  status: ClientStatus | null
}

/** Закрытые без решения банка: в toClientStatus их нет, а в списке им место среди завершённых */
const CLOSED_STATUS: Partial<Record<string, ClientStatus>> = { cancelled: 'cancelled', offer_declined: 'declined', expired: 'expired' }

function rowOf(item: AssistantApplicationDto): Row {
  const status = toClientStatus(item.status as ApplicationStatusCode, item.client_stage) ?? CLOSED_STATUS[item.status] ?? null
  const product = products.value?.find((entry) => entry.code === item.product_code)?.title ?? item.product_code
  const statusLabel = status ? CLIENT_STATUS_META[status].label : (item.client_stage ?? item.status)
  return { id: item.id, title: product, subtitle: `№ ${item.number} · ${statusLabel}`, status }
}

const rows = computed(() => props.applications.map(rowOf))
const filtered = computed(() => {
  const text = query.value.trim().toLowerCase()
  return text ? rows.value.filter((row) => `${row.title} ${row.subtitle}`.toLowerCase().includes(text)) : rows.value
})
const groups = computed(() => {
  const isClosed = (row: Row) => row.status !== null && CLOSED_CLIENT_STATUSES.includes(row.status)
  return [
    { title: 'В работе', rows: filtered.value.filter((row) => !isClosed(row)) },
    { title: 'Завершённые', rows: filtered.value.filter(isClosed) },
  ].filter((group) => group.rows.length)
})
const GENERAL: Row = { id: null, title: 'Без заявки — общие вопросы о кредитах', subtitle: '', status: null }
/** Порядок для стрелок: как в списке сверху вниз */
const options = computed<Row[]>(() => [...groups.value.flatMap((group) => group.rows), GENERAL])
const selected = computed(() => rows.value.find((row) => row.id === props.selectedId) ?? null)
const showSearch = computed(() => rows.value.length > 5)

function dot(row: Row): string {
  return row.status ? DOT_CLASS[CLIENT_STATUS_META[row.status].tone] : DOT_CLASS.glass
}
function optionId(index: number): string {
  return `${id}-option-${index}`
}
function indexOf(row: Row): number {
  return options.value.findIndex((option) => option.id === row.id)
}

function show() {
  open.value = true
  query.value = ''
  active.value = Math.max(options.value.findIndex((option) => option.id === props.selectedId), 0)
  void nextTick(() => (showSearch.value ? search.value : root.value?.querySelector<HTMLElement>('[role="listbox"]'))?.focus())
}
function hide(focusTrigger = true) {
  open.value = false
  if (focusTrigger) void nextTick(() => root.value?.querySelector<HTMLElement>('[data-trigger]')?.focus())
}
function choose(row: Row) {
  emit('select', row.id)
  hide()
}

function onKeydown(event: KeyboardEvent) {
  if (!open.value) {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      if ((event.target as HTMLElement).dataset.trigger === undefined) return
      event.preventDefault()
      show()
    }
    return
  }
  if (event.key === 'Escape') {
    // Esc закрывает список, а не всё окно помощника
    event.stopPropagation()
    event.preventDefault()
    hide()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const count = options.value.length
    active.value = (active.value + (event.key === 'ArrowDown' ? 1 : -1) + count) % count
    void nextTick(() => document.getElementById(optionId(active.value))?.scrollIntoView({ block: 'nearest' }))
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const row = options.value[active.value]
    if (row) choose(row)
  } else if (event.key === 'Tab') {
    hide(false)
  }
}

watch(query, () => (active.value = 0))

function onPointerDown(event: PointerEvent) {
  if (open.value && root.value && !root.value.contains(event.target as Node)) hide(false)
}
watch(open, (value) => {
  if (value) document.addEventListener('pointerdown', onPointerDown, true)
  else document.removeEventListener('pointerdown', onPointerDown, true)
})
onBeforeUnmount(() => document.removeEventListener('pointerdown', onPointerDown, true))
</script>

<template>
  <div ref="root" class="relative" @keydown="onKeydown">
    <span :id="`${id}-label`" class="mb-1.5 block text-xs text-on-night-secondary">Спрашиваю про</span>
    <button
      type="button"
      data-trigger
      class="flex w-full items-center gap-3 rounded-2xl bg-night-glass px-3.5 py-2.5 text-left transition-shadow hover:bg-night-line"
      :class="open ? 'ring-2 ring-brand' : 'ring-1 ring-night-line'"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-labelledby="`${id}-label ${id}-value`"
      @click="open ? hide() : show()"
    >
      <span class="size-2.5 shrink-0 rounded-full" :class="selected ? dot(selected) : DOT_CLASS.glass" aria-hidden="true" />
      <span :id="`${id}-value`" class="flex min-w-0 flex-1 flex-col">
        <span class="truncate text-sm font-bold text-on-night">{{ selected ? selected.title : 'Общие вопросы' }}</span>
        <span class="truncate text-xs text-on-night-secondary">{{ selected ? selected.subtitle : 'без привязки к заявке' }}</span>
      </span>
      <ChevronDown class="picker__chevron size-4 shrink-0 text-on-night-secondary" :class="open && 'rotate-180'" aria-hidden="true" />
    </button>

    <Transition name="picker">
      <div
        v-if="open"
        class="absolute inset-x-0 top-full z-20 mt-2 rounded-2xl bg-night-elevated p-1.5 shadow-[0_0_0_1px_var(--color-night-line),0_18px_40px_rgb(0_0_0/0.55)]"
      >
        <label v-if="showSearch" class="mb-1 flex items-center gap-2 rounded-xl bg-night-glass px-3 py-2">
          <Search class="size-4 shrink-0 text-on-night-secondary" aria-hidden="true" />
          <span class="sr-only">Найти заявку</span>
          <input
            ref="search"
            v-model="query"
            type="search"
            class="min-w-0 flex-1 bg-transparent text-sm text-on-night placeholder:text-on-night-secondary focus:outline-none"
            placeholder="Номер или продукт"
            :aria-controls="`${id}-listbox`"
            :aria-activedescendant="optionId(active)"
          />
        </label>
        <ul
          :id="`${id}-listbox`"
          role="listbox"
          tabindex="-1"
          :aria-labelledby="`${id}-label`"
          :aria-activedescendant="optionId(active)"
          class="max-h-80 overflow-y-auto overscroll-contain focus:outline-none"
        >
          <template v-for="group in groups" :key="group.title">
            <li role="presentation" class="px-2.5 pt-2.5 pb-1 text-[0.6875rem] font-bold tracking-wider text-on-night-secondary uppercase">
              {{ group.title }}
            </li>
            <li
              v-for="row in group.rows"
              :id="optionId(indexOf(row))"
              :key="row.id ?? 'general'"
              role="option"
              :aria-selected="row.id === selectedId"
              class="flex cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2.5"
              :class="active === indexOf(row) ? 'bg-night-glass' : ''"
              @pointerenter="active = indexOf(row)"
              @click="choose(row)"
            >
              <span class="size-2 shrink-0 rounded-full" :class="dot(row)" aria-hidden="true" />
              <span class="flex min-w-0 flex-1 flex-col">
                <span class="truncate text-sm font-semibold text-on-night">{{ row.title }}</span>
                <span class="truncate text-xs text-on-night-secondary">{{ row.subtitle }}</span>
              </span>
              <Check v-if="row.id === selectedId" class="size-4 shrink-0 text-brand" aria-hidden="true" />
            </li>
          </template>
          <li v-if="!groups.length" role="presentation" class="px-2.5 py-3 text-sm text-on-night-secondary">Ничего не нашли</li>
          <li role="presentation" class="mx-1.5 my-1 h-px bg-night-line" />
          <li
            :id="optionId(options.length - 1)"
            role="option"
            :aria-selected="selectedId === null"
            class="flex cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2.5"
            :class="active === options.length - 1 ? 'bg-night-glass' : ''"
            @pointerenter="active = options.length - 1"
            @click="choose(GENERAL)"
          >
            <span class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-night-glass" aria-hidden="true">
              <MessageSquare class="size-3.5 text-on-night" />
            </span>
            <span class="flex-1 text-sm font-semibold text-on-night">{{ GENERAL.title }}</span>
            <Check v-if="selectedId === null" class="size-4 shrink-0 text-brand" aria-hidden="true" />
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.picker__chevron {
  transition: transform 0.2s ease;
}
.picker-enter-active,
.picker-leave-active {
  transition:
    opacity 0.16s ease,
    transform 0.18s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.picker-enter-from,
.picker-leave-to {
  opacity: 0;
  transform: translateY(-0.25rem) scale(0.98);
}
@media (prefers-reduced-motion: reduce) {
  .picker__chevron,
  .picker-enter-active,
  .picker-leave-active {
    transition: none;
  }
}
</style>
