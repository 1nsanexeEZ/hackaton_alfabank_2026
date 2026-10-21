<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description?: string
    /** Светлый текст для тёмного фона */
    inverted?: boolean
  }>(),
  { description: undefined, inverted: false },
)
</script>

<template>
  <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
    <div class="max-w-3xl">
      <h2 class="text-title" :class="inverted ? 'text-on-night' : 'text-ink'">{{ title }}</h2>
      <p
        v-if="description"
        class="text-lead mt-3"
        :class="inverted ? 'text-on-night-secondary' : 'text-ink-secondary'"
      >
        {{ description }}
      </p>
      <slot name="after" />
    </div>
    <slot name="aside" />
  </div>
</template>
