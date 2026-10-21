<script setup lang="ts">
import { APP_NAME, APP_TAGLINE } from '../config'

withDefaults(defineProps<{ inverted?: boolean }>(), { inverted: false })
</script>

<template>
  <span class="inline-flex items-center gap-2.5">
    <svg viewBox="0 0 32 32" class="size-8 shrink-0" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#ef3124" />
      <path d="M16 7 9.5 23h3.2l1.3-3.4h4l1.3 3.4h3.2L16 7Zm-1.1 10.2L16 14l1.1 3.2h-2.2Z" fill="#fff" />
      <rect x="9.5" y="24.5" width="13" height="2" rx="1" fill="#fff" />
    </svg>
    <span class="flex flex-col leading-tight whitespace-nowrap">
      <span class="text-[15px] font-bold" :class="inverted ? 'text-on-night' : 'text-ink'">
        {{ APP_NAME }}
      </span>
      <span class="text-xs" :class="inverted ? 'text-on-night-secondary' : 'text-ink-secondary'">
        {{ APP_TAGLINE }}
      </span>
    </span>
  </span>
</template>
