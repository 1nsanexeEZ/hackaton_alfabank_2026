<script setup lang="ts">
import { Check } from 'lucide-vue-next'
import { useId } from 'vue'

defineProps<{ error?: string }>()

const model = defineModel<boolean>({ required: true })

const id = useId()
</script>

<template>
  <div>
    <label :for="id" class="flex cursor-pointer items-start gap-3 text-sm text-ink-secondary">
      <span class="relative mt-0.5 flex size-5 shrink-0">
        <input
          :id="id"
          v-model="model"
          type="checkbox"
          :aria-invalid="Boolean(error)"
          class="peer size-5 cursor-pointer appearance-none rounded-md border-2 border-ink-muted transition checked:border-brand checked:bg-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          :class="error && 'border-brand'"
        />
        <Check
          class="pointer-events-none absolute inset-0 m-auto size-3.5 text-white opacity-0 peer-checked:opacity-100"
          :stroke-width="3"
          aria-hidden="true"
        />
      </span>
      <span><slot /></span>
    </label>
    <p v-if="error" class="mt-1.5 pl-8 text-sm text-brand">{{ error }}</p>
  </div>
</template>
