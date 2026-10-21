<script setup lang="ts">
/** Белая панель рабочего кабинета: заголовок, действия справа и содержимое */
withDefaults(defineProps<{ title?: string; description?: string; flush?: boolean }>(), {
  title: undefined,
  description: undefined,
  flush: false,
})
</script>

<template>
  <section class="rounded-2xl bg-white ring-1 ring-line">
    <header
      v-if="title || $slots.actions"
      class="flex flex-wrap items-start justify-between gap-3 px-5 pt-5"
      :class="flush && 'pb-4'"
    >
      <div v-if="title">
        <h2 class="text-base font-bold text-ink">{{ title }}</h2>
        <p v-if="description" class="mt-0.5 text-sm text-ink-secondary">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div :class="flush ? '' : 'p-5'">
      <slot />
    </div>
  </section>
</template>
