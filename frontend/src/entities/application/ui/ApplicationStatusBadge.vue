<script setup lang="ts">
import { computed } from 'vue'

import { BaseBadge } from '@/shared/ui'

import { APPLICATION_STATUS_META } from '../model/status'
import type { ApplicationStatus } from '../model/types'

const props = defineProps<{ status: ApplicationStatus }>()

const meta = computed(() => APPLICATION_STATUS_META[props.status])
</script>

<template>
  <BaseBadge :tone="meta.tone">{{ meta.label }}</BaseBadge>
</template>
