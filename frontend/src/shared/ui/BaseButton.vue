<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

type Variant = 'primary' | 'secondary' | 'ghost' | 'inverted' | 'glass'
type Size = 's' | 'm' | 'l'

const props = withDefaults(
  defineProps<{
    variant?: Variant
    size?: Size
    /** Внешняя ссылка или якорь — рендерится <a> */
    href?: string
    /** Маршрут приложения — рендерится RouterLink */
    to?: RouteLocationRaw
    type?: 'button' | 'submit' | 'reset'
    block?: boolean
    disabled?: boolean
    loading?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'm',
    href: undefined,
    to: undefined,
    type: 'button',
    block: false,
    disabled: false,
    loading: false,
  },
)

const VARIANT_CLASS: Record<Variant, string> = {
  primary: 'bg-brand text-white hover:bg-brand-hover active:bg-brand-active',
  secondary: 'bg-surface text-ink hover:bg-surface-strong',
  ghost: 'text-ink hover:bg-surface',
  // Белая кнопка на тёмном фоне
  inverted: 'bg-white text-ink hover:bg-white/85',
  // Второстепенная кнопка на тёмном фоне
  glass: 'bg-night-glass text-on-night hover:bg-white/15',
}

const SIZE_CLASS: Record<Size, string> = {
  s: 'h-10 px-4 text-sm',
  m: 'h-12 px-5 text-base',
  l: 'h-14 px-7 text-base',
}

const tag = computed(() => (props.to ? RouterLink : props.href ? 'a' : 'button'))

const tagAttrs = computed(() => {
  if (props.to) return { to: props.to }
  if (props.href) return { href: props.href }
  return { type: props.type, disabled: props.disabled || props.loading }
})
</script>

<template>
  <component
    :is="tag"
    v-bind="tagAttrs"
    :aria-busy="loading || undefined"
    :class="[
      'inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap transition-colors select-none',
      'disabled:pointer-events-none disabled:opacity-50',
      VARIANT_CLASS[variant],
      SIZE_CLASS[size],
      block && 'w-full',
    ]"
  >
    <span
      v-if="loading"
      class="size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
      aria-hidden="true"
    />
    <slot />
  </component>
</template>
