<script setup lang="ts">
import { Building2, ChartLine, LockKeyhole } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { formatDate } from '@/shared/lib'
import { BaseButton } from '@/shared/ui'

/**
 * Одно согласие: что оно даёт банку простыми словами, статус, сколько осталось, закон и редакция текста.
 * Отзыв подтверждается прямо в карточке — без модалки и без потери контекста.
 */
const props = defineProps<{
  icon: 'personal' | 'bureau' | 'company'
  title: string
  /** Подзаголовок: компания и ИНН у согласия компании */
  caption?: string
  description: string
  law: string
  /** Полный текст согласия — раскрывается по ссылке */
  body: string
  active: boolean
  /** Подпись статуса, когда согласие не действует: «Отозвано 24 окт.», «Не давали» */
  inactiveLabel: string
  givenAt?: string | null
  validUntil?: string | null
  textVersion?: string | null
  revocable: boolean
  revoking: boolean
  confirmText: string
}>()

const emit = defineEmits<{ revoke: [] }>()

const confirming = ref(false)
const showText = ref(false)
// Согласие отозвано или стало недоступно — подтверждение больше не нужно
watch(
  () => props.active && props.revocable,
  (value) => {
    if (!value) confirming.value = false
  },
)

const ICON = { personal: LockKeyhole, bureau: ChartLine, company: Building2 } as const

const DAY = 86_400_000

/** Доля оставшегося срока и подпись «осталось …»; бессрочное — без полоски */
const term = computed(() => {
  if (!props.active || !props.validUntil || !props.givenAt) return null
  const end = new Date(props.validUntil).getTime()
  const start = new Date(props.givenAt).getTime()
  const now = Date.now()
  const left = Math.max(end - now, 0)
  const share = end > start ? Math.min(Math.max(left / (end - start), 0), 1) : 0
  const days = Math.ceil(left / DAY)
  const label = days > 45 ? `осталось ${Math.round(days / 30)} мес.` : `осталось ${days} дн.`
  return { share, label, soon: days <= 30 }
})

const status = computed(() => {
  if (!props.active) return { label: props.inactiveLabel, class: 'bg-surface text-ink-secondary' }
  if (!props.validUntil) return { label: 'Бессрочно', class: 'bg-success-soft text-success' }
  return term.value?.soon
    ? { label: 'Скоро истекает', class: 'bg-warning-soft text-warning' }
    : { label: 'Действует', class: 'bg-success-soft text-success' }
})
</script>

<template>
  <article class="overflow-hidden rounded-2xl ring-1 ring-line">
    <div class="grid grid-cols-[2.75rem_minmax(0,1fr)] gap-x-4 gap-y-3 p-4 sm:grid-cols-[2.75rem_minmax(0,1fr)_auto] sm:p-5">
      <span
        class="flex size-11 items-center justify-center rounded-xl"
        :class="icon === 'company' ? 'bg-night text-white' : icon === 'bureau' ? 'bg-info-soft text-info' : 'bg-surface text-ink'"
        aria-hidden="true"
      >
        <component :is="ICON[icon]" class="size-5" />
      </span>

      <div class="min-w-0 space-y-2">
        <p v-if="caption" class="text-[0.8125rem] font-semibold text-ink-secondary">{{ caption }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <h4 class="text-base font-bold text-ink">{{ title }}</h4>
          <span class="rounded-full px-2.5 py-0.5 text-xs font-bold" :class="status.class">{{ status.label }}</span>
        </div>
        <p class="text-sm leading-relaxed text-ink-secondary">{{ description }}</p>

        <div v-if="term" class="space-y-1.5 pt-0.5">
          <div class="flex flex-wrap justify-between gap-x-3 text-xs text-ink-secondary">
            <span v-if="givenAt">Дано {{ formatDate(givenAt) }}</span>
            <span class="font-semibold" :class="term.soon ? 'text-warning' : 'text-ink'">
              до {{ formatDate(validUntil!) }} · {{ term.label }}
            </span>
          </div>
          <div class="h-1.5 overflow-hidden rounded-full bg-surface-strong" aria-hidden="true">
            <span class="consent__bar block h-full rounded-full" :class="term.soon ? 'bg-warning' : 'bg-success'" :style="{ width: `${term.share * 100}%` }" />
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-1.5 text-xs text-ink-secondary">
          <span class="rounded-md bg-surface-soft px-2 py-0.5">{{ law }}</span>
          <span v-if="active && givenAt && !term" class="rounded-md bg-surface-soft px-2 py-0.5">дано {{ formatDate(givenAt) }}</span>
          <span v-if="textVersion" class="rounded-md bg-surface-soft px-2 py-0.5">редакция {{ textVersion }}</span>
          <button type="button" class="font-medium text-info underline-offset-2 hover:underline" :aria-expanded="showText" @click="showText = !showText">
            {{ showText ? 'Скрыть текст' : 'Текст согласия' }}
          </button>
        </div>
        <p v-if="showText" class="rounded-xl bg-surface-soft p-3 text-xs leading-relaxed text-ink-secondary">{{ body }}</p>

        <!-- Не действует: дать согласие (кнопка или подсказка от родителя) -->
        <div v-if="!active" class="pt-1">
          <slot />
        </div>
      </div>

      <div v-if="active && revocable && !confirming" class="col-start-2 sm:col-start-3 sm:row-start-1">
        <button
          type="button"
          class="h-10 rounded-xl px-3.5 text-sm font-semibold text-brand-active ring-1 ring-line transition-colors hover:bg-brand-soft"
          @click="confirming = true"
        >
          Отозвать
        </button>
      </div>
    </div>

    <!-- Подтверждение отзыва — полосой внизу карточки -->
    <div v-if="active && confirming" class="flex flex-wrap items-center gap-3 bg-brand-soft px-4 py-3.5 sm:px-5" role="alert">
      <p class="min-w-[14rem] flex-1 text-sm text-ink"><b>Отозвать согласие?</b> {{ confirmText }}</p>
      <BaseButton variant="secondary" size="s" :disabled="revoking" @click="confirming = false">Оставить</BaseButton>
      <BaseButton size="s" :loading="revoking" @click="emit('revoke')">Отозвать</BaseButton>
    </div>
  </article>
</template>

<style scoped>
.consent__bar {
  transition: width 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
}
@media (prefers-reduced-motion: reduce) {
  .consent__bar {
    transition: none;
  }
}
</style>
